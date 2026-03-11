"""Entry point for the SentinelAI log shipping agent."""

from __future__ import annotations

import argparse
import logging
import queue
import signal
import threading
import time

from config import load_config
from sender import LogSender
from watcher import LogWatcher


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SentinelAI lightweight log agent")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the YAML config file",
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = parse_args()
    config = load_config(args.config)

    log_queue: "queue.Queue[dict[str, str]]" = queue.Queue(maxsize=config.queue_size)
    stop_event = threading.Event()

    def request_shutdown(signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info("Received signal %s, shutting down", signum)
        stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, request_shutdown)

    watcher = LogWatcher(
        targets=config.logs,
        output_queue=log_queue,
        stop_event=stop_event,
        poll_interval=config.poll_interval,
    )
    sender = LogSender(
        config=config.sentinel,
        input_queue=log_queue,
        stop_event=stop_event,
    )

    watcher.start()
    sender.start()

    try:
        while not stop_event.is_set():
            if not watcher.is_alive():
                logging.getLogger(__name__).error("Watcher thread exited unexpectedly")
                stop_event.set()
                return 1
            if not sender.is_alive():
                logging.getLogger(__name__).error("Sender thread exited unexpectedly")
                stop_event.set()
                return 1
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        watcher.join(timeout=5)
        sender.join(timeout=5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
