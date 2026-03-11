"""Configuration loading for the SentinelAI log agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_BATCH_SIZE = 20
DEFAULT_FLUSH_INTERVAL = 1.0
DEFAULT_POLL_INTERVAL = 0.25
DEFAULT_QUEUE_SIZE = 10000
DEFAULT_REQUEST_TIMEOUT = 5.0
DEFAULT_MAX_BACKOFF = 30.0


@dataclass(frozen=True)
class SentinelConfig:
    server: str
    api_key: str
    batch_size: int = DEFAULT_BATCH_SIZE
    flush_interval: float = DEFAULT_FLUSH_INTERVAL
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    max_backoff: float = DEFAULT_MAX_BACKOFF


@dataclass(frozen=True)
class LogTarget:
    path: str
    source: str


@dataclass(frozen=True)
class AgentConfig:
    sentinel: SentinelConfig
    logs: list[LogTarget]
    poll_interval: float = DEFAULT_POLL_INTERVAL
    queue_size: int = DEFAULT_QUEUE_SIZE


def _require_mapping(data: object, section: str) -> dict:
    if not isinstance(data, dict):
        raise ValueError(f"'{section}' must be a mapping")
    return data


def _require_non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field_name}' must be a non-empty string")
    return value.strip()


def load_config(path: str | Path) -> AgentConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")

    sentinel_raw = _require_mapping(raw.get("sentinel"), "sentinel")
    server = _require_non_empty_string(sentinel_raw.get("server"), "sentinel.server").rstrip("/")
    api_key = _require_non_empty_string(sentinel_raw.get("api_key"), "sentinel.api_key")
    batch_size = int(sentinel_raw.get("batch_size", DEFAULT_BATCH_SIZE))
    flush_interval = float(sentinel_raw.get("flush_interval", DEFAULT_FLUSH_INTERVAL))
    request_timeout = float(sentinel_raw.get("request_timeout", DEFAULT_REQUEST_TIMEOUT))
    max_backoff = float(sentinel_raw.get("max_backoff", DEFAULT_MAX_BACKOFF))

    if batch_size < 1 or batch_size > 20:
        raise ValueError("'sentinel.batch_size' must be between 1 and 20")
    if flush_interval <= 0:
        raise ValueError("'sentinel.flush_interval' must be greater than 0")
    if request_timeout <= 0:
        raise ValueError("'sentinel.request_timeout' must be greater than 0")
    if max_backoff < 1:
        raise ValueError("'sentinel.max_backoff' must be at least 1 second")

    logs_raw = raw.get("logs")
    if not isinstance(logs_raw, list) or not logs_raw:
        raise ValueError("'logs' must be a non-empty list")

    log_targets: list[LogTarget] = []
    for index, item in enumerate(logs_raw):
        section = f"logs[{index}]"
        item_raw = _require_mapping(item, section)
        log_targets.append(
            LogTarget(
                path=_require_non_empty_string(item_raw.get("path"), f"{section}.path"),
                source=_require_non_empty_string(item_raw.get("source"), f"{section}.source"),
            )
        )

    poll_interval = float(raw.get("poll_interval", DEFAULT_POLL_INTERVAL))
    queue_size = int(raw.get("queue_size", DEFAULT_QUEUE_SIZE))
    if poll_interval <= 0:
        raise ValueError("'poll_interval' must be greater than 0")
    if queue_size < 100:
        raise ValueError("'queue_size' must be at least 100")

    return AgentConfig(
        sentinel=SentinelConfig(
            server=server,
            api_key=api_key,
            batch_size=batch_size,
            flush_interval=flush_interval,
            request_timeout=request_timeout,
            max_backoff=max_backoff,
        ),
        logs=log_targets,
        poll_interval=poll_interval,
        queue_size=queue_size,
    )
