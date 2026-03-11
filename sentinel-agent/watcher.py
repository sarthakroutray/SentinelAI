"""Polling log watcher with simple tail and rotation handling."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from dataclasses import dataclass

from config import LogTarget
from parser import parse_log_line

logger = logging.getLogger(__name__)


def _file_signature(stat_result: os.stat_result) -> tuple[int, int]:
    return (stat_result.st_dev, stat_result.st_ino)


@dataclass
class FileState:
    target: LogTarget
    handle: object | None = None
    signature: tuple[int, int] | None = None

    def close(self) -> None:
        if self.handle is not None:
            try:
                self.handle.close()
            except OSError:
                logger.warning("Failed closing %s", self.target.path, exc_info=True)
            finally:
                self.handle = None
                self.signature = None

    def _open(self, start_at_end: bool) -> None:
        stat_result = os.stat(self.target.path)
        handle = open(self.target.path, "r", encoding="utf-8", errors="replace")
        if start_at_end:
            handle.seek(0, os.SEEK_END)
        self.handle = handle
        self.signature = _file_signature(stat_result)
        logger.info("Watching %s as %s", self.target.path, self.target.source)

    def _read_available_lines(self) -> list[str]:
        if self.handle is None:
            return []

        lines: list[str] = []
        while True:
            position = self.handle.tell()
            line = self.handle.readline()
            if not line:
                break
            if not line.endswith("\n"):
                self.handle.seek(position)
                break
            lines.append(line.rstrip("\r\n"))
        return lines

    def _needs_reopen(self) -> bool:
        if self.handle is None or self.signature is None:
            return False

        try:
            current_stat = os.stat(self.target.path)
        except FileNotFoundError:
            return False

        current_signature = _file_signature(current_stat)
        current_position = self.handle.tell()
        return current_signature != self.signature or current_stat.st_size < current_position

    def poll(self) -> list[str]:
        try:
            if self.handle is None:
                try:
                    self._open(start_at_end=True)
                except FileNotFoundError:
                    return []

            lines = self._read_available_lines()
            if self._needs_reopen():
                self.close()
                try:
                    self._open(start_at_end=False)
                except FileNotFoundError:
                    return lines
                lines.extend(self._read_available_lines())
            return lines
        except OSError:
            logger.warning("Temporary read error on %s", self.target.path, exc_info=True)
            self.close()
            return []


class LogWatcher(threading.Thread):
    def __init__(
        self,
        targets: list[LogTarget],
        output_queue: "queue.Queue[dict[str, str]]",
        stop_event: threading.Event,
        poll_interval: float,
    ) -> None:
        super().__init__(name="log-watcher", daemon=True)
        self._states = [FileState(target=target) for target in targets]
        self._output_queue = output_queue
        self._stop_event = stop_event
        self._poll_interval = poll_interval

    def run(self) -> None:
        while not self._stop_event.is_set():
            for state in self._states:
                for line in state.poll():
                    payload = parse_log_line(state.target.source, line)
                    self._output_queue.put(payload)
            self._stop_event.wait(self._poll_interval)

        for state in self._states:
            state.close()
