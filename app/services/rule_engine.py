"""Rule engine – evaluates incoming logs and returns alert severity + reason.

⚠ SINGLE-WORKER CONSTRAINT
   The per-IP burst tracker (``_IpTracker``) is held in-memory.  Each
   worker process maintains an independent set of rate-limit buckets.
   Deploy a single alert-worker instance for consistent rule evaluation.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.config import settings


@dataclass(slots=True)
class _IpTracker:
    """In-memory sliding-window tracker for per-IP log rates."""

    window_seconds: int = field(default_factory=lambda: settings.IP_RATE_WINDOW_SECONDS)
    threshold: int = field(default_factory=lambda: settings.IP_RATE_THRESHOLD)
    _buckets: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def record(self, ip: str) -> bool:
        """Record a log event for *ip* and return True if threshold exceeded."""
        now = time.monotonic()
        q = self._buckets[ip]
        q.append(now)
        # Evict entries outside the window
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        return len(q) > self.threshold


# Module-level singleton (acceptable for Phase 1)
_ip_tracker = _IpTracker()


@dataclass(frozen=True, slots=True)
class RuleResult:
    severity: str  # "HIGH" | "MEDIUM" | None → no alert
    reason: str


_HIGH_KEYWORDS = ("failed login", "unauthorized")


def evaluate(log_level: str, message: str, ip_address: str | None) -> RuleResult | None:
    """Run rule checks against a single log entry.

    Returns a ``RuleResult`` when an alert should be raised, or ``None`` otherwise.
    """
    level = log_level.upper()
    msg_lower = message.lower()

    # ── HIGH severity rules ──────────────────────────────────────────
    if level == "ERROR":
        return RuleResult(severity="HIGH", reason="Log level is ERROR")

    for keyword in _HIGH_KEYWORDS:
        if keyword in msg_lower:
            return RuleResult(
                severity="HIGH",
                reason=f'Message contains "{keyword}"',
            )

    # ── MEDIUM severity rules ────────────────────────────────────────
    if ip_address and _ip_tracker.record(ip_address):
        return RuleResult(
            severity="MEDIUM",
            reason=(
                f"More than {_ip_tracker.threshold} logs from IP {ip_address} "
                f"within {_ip_tracker.window_seconds}s"
            ),
        )

    return None
