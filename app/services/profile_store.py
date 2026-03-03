"""In-memory IP / source profile store for statistical anomaly detection."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.config import settings


@dataclass
class _IpProfile:
    """Tracks per-IP (timestamp, is_error) events within a sliding window."""
    events: deque = field(default_factory=lambda: deque())  # deque of (float, bool)


class ProfileStore:
    """Sliding-window statistics per IP address."""

    def __init__(self, window: int | None = None) -> None:
        self._window = window or settings.IP_RATE_WINDOW_SECONDS
        self._profiles: dict[str, _IpProfile] = defaultdict(_IpProfile)
        self._lock = threading.Lock()
        # Global rolling events for spike detection: (timestamp, is_error) tuples
        self._global_events: deque[tuple[float, bool]] = deque()

    def record(self, ip: str | None, is_error: bool) -> dict:
        """Record an event and return current statistics snapshot."""
        now = time.monotonic()
        with self._lock:
            # Global tracking
            self._global_events.append((now, is_error))
            self._evict_global(now)

            if ip is None:
                return self._global_snapshot()

            prof = self._profiles[ip]
            prof.events.append((now, is_error))

            # Evict stale entries for this IP
            cutoff = now - self._window
            while prof.events and prof.events[0][0] < cutoff:
                prof.events.popleft()

            ip_rate = len(prof.events)
            windowed_errors = sum(1 for _, err in prof.events if err)
            ip_error_ratio = windowed_errors / max(ip_rate, 1)

            global_rate = len(self._global_events)
            global_errors = sum(1 for _, err in self._global_events if err)
            global_error_ratio = global_errors / max(global_rate, 1)

            return {
                "ip_rate": ip_rate,
                "ip_error_ratio": ip_error_ratio,
                "global_rate": global_rate,
                "global_error_ratio": global_error_ratio,
            }

    def _evict_global(self, now: float) -> None:
        cutoff = now - self._window
        while self._global_events and self._global_events[0][0] < cutoff:
            self._global_events.popleft()

    def _global_snapshot(self) -> dict:
        global_rate = len(self._global_events)
        global_errors = sum(1 for _, err in self._global_events if err)
        global_error_ratio = global_errors / max(global_rate, 1)
        return {
            "ip_rate": 0,
            "ip_error_ratio": 0.0,
            "global_rate": global_rate,
            "global_error_ratio": global_error_ratio,
        }

    def clear(self) -> None:
        with self._lock:
            self._profiles.clear()
            self._global_events.clear()


# Module-level singleton
profile_store = ProfileStore()
