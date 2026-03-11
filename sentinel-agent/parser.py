"""Parsing helpers that convert raw log lines to SentinelAI payloads."""

from __future__ import annotations

import re
from datetime import datetime, timezone


IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
ISO_TS_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b"
)
SYSLOG_TS_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"(\d{1,2})\s+"
    r"(\d{2}:\d{2}:\d{2})"
)

LEVEL_KEYWORDS = (
    ("CRITICAL", ("CRITICAL", "FATAL", "PANIC", "EMERG", "ALERT")),
    ("ERROR", ("ERROR", "ERR", "FAILED", "FAILURE", "DENIED", "EXCEPTION")),
    ("WARNING", ("WARNING", "WARN", "INVALID", "REJECTED", "TIMEOUT")),
)


def detect_log_level(message: str) -> str:
    upper_message = message.upper()
    for level, keywords in LEVEL_KEYWORDS:
        if any(keyword in upper_message for keyword in keywords):
            return level
    return "INFO"


def extract_ipv4(message: str) -> str:
    match = IPV4_RE.search(message)
    return match.group(0) if match else "127.0.0.1"


def parse_timestamp(message: str) -> str:
    now = datetime.now(timezone.utc)

    iso_match = ISO_TS_RE.search(message)
    if iso_match:
        raw_value = iso_match.group(0)
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    syslog_match = SYSLOG_TS_RE.match(message)
    if syslog_match:
        month, day, clock = syslog_match.groups()
        parsed = datetime.strptime(
            f"{now.year} {month} {day} {clock}",
            "%Y %b %d %H:%M:%S",
        ).replace(tzinfo=timezone.utc)
        if parsed > now:
            parsed = parsed.replace(year=parsed.year - 1)
        return parsed.isoformat()

    return now.isoformat()


def parse_log_line(source: str, line: str) -> dict[str, str]:
    message = line.strip()
    return {
        "source": source,
        "log_level": detect_log_level(message),
        "message": message,
        "timestamp": parse_timestamp(message),
        "ip_address": extract_ipv4(message),
    }
