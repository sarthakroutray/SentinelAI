"""Buffered HTTP sender with batching and retry handling."""

from __future__ import annotations

import logging
import queue
import threading
from time import sleep

import requests

from config import SentinelConfig

logger = logging.getLogger(__name__)


class LogSender(threading.Thread):
    def __init__(
        self,
        config: SentinelConfig,
        input_queue: "queue.Queue[dict[str, str]]",
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="log-sender", daemon=True)
        self._config = config
        self._input_queue = input_queue
        self._stop_event = stop_event
        self._session = requests.Session()
        self._headers = {
            "Content-Type": "application/json",
            "X-API-Key": config.api_key,
        }
        self._endpoint = f"{config.server}/logs"

    def run(self) -> None:
        batch: list[dict[str, str]] = []

        while not self._stop_event.is_set():
            timeout = self._config.flush_interval if not batch else max(self._config.flush_interval, 0.1)
            try:
                item = self._input_queue.get(timeout=timeout)
                batch.append(item)
                if len(batch) >= self._config.batch_size:
                    self._flush_batch(batch)
                    batch = []
            except queue.Empty:
                if batch:
                    self._flush_batch(batch)
                    batch = []

        while True:
            try:
                batch.append(self._input_queue.get_nowait())
            except queue.Empty:
                break

        if batch:
            self._flush_batch(batch)

        self._session.close()

    def _flush_batch(self, batch: list[dict[str, str]]) -> None:
        pending = list(batch)
        attempt = 0

        while pending and not self._stop_event.is_set():
            try:
                pending = self._send_pending(pending)
                attempt = 0
            except requests.RequestException as exc:
                attempt += 1
                backoff = min(self._config.max_backoff, float(2 ** min(attempt, 5)))
                logger.warning(
                    "Send failed for %s log(s): %s. Retrying in %.1fs",
                    len(pending),
                    exc,
                    backoff,
                )
                sleep(backoff)

        if pending and self._stop_event.is_set():
            logger.warning(
                "Agent stopped before flushing %s queued log(s)",
                len(pending),
            )

    def _send_pending(self, pending: list[dict[str, str]]) -> list[dict[str, str]]:
        unsent: list[dict[str, str]] = []

        for index, payload in enumerate(pending):
            response = self._session.post(
                self._endpoint,
                headers=self._headers,
                json=payload,
                timeout=self._config.request_timeout,
            )

            if 200 <= response.status_code < 300:
                continue

            if response.status_code in (400, 401, 403, 404, 422):
                logger.error(
                    "Dropping log due to permanent API error %s: %s",
                    response.status_code,
                    response.text.strip(),
                )
                continue

            unsent = pending[index:]
            raise requests.RequestException(
                f"HTTP {response.status_code}: {response.text.strip()}"
            )

        return unsent
