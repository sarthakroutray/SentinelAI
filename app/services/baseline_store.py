"""Contamination-safe baseline buffer for IsolationForest training.

Only stores feature vectors from low-risk, non-anomalous logs.
Thread-safe sliding window with configurable max size.

⚠ SINGLE-WORKER CONSTRAINT
   This store is held entirely in-memory.  Each worker process maintains
   an independent buffer.  Deploy a single alert-worker instance for
   consistent model training data.
"""

from __future__ import annotations

import threading
from collections import deque

import numpy as np

from app.config import settings

# Hard-coded feature dimensionality — must match extract_features() in statistical_engine.py
FEATURE_DIM: int = 4


class BaselineStore:
    """In-memory ring buffer of known-good feature vectors.

    Per-IP quota prevents any single source from dominating the training
    distribution, reducing the blast radius of a cold-start baseline poisoning
    attack.
    """

    # Maximum fraction of total buffer any single IP may occupy
    _MAX_PER_IP_FRACTION: float = 0.05

    def __init__(self, max_size: int | None = None) -> None:
        self._max_size = max_size or settings.BASELINE_BUFFER_MAX
        self._buffer: deque[list[float]] = deque(maxlen=self._max_size)
        # Parallel deque tracking which IP each vector came from (None = unknown)
        self._ip_buffer: deque[str | None] = deque(maxlen=self._max_size)
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────

    def add(self, features: list[float], ip: str | None = None) -> None:
        """Append a feature vector to the baseline (thread-safe).

        Args:
            features: Feature vector of length FEATURE_DIM.
            ip: Source IP of the log, used to enforce per-IP quota.

        Raises:
            ValueError: If features doesn't have exactly FEATURE_DIM elements.
        """
        if len(features) != FEATURE_DIM:
            raise ValueError(
                f"Feature vector must have exactly {FEATURE_DIM} elements, "
                f"got {len(features)}"
            )

        with self._lock:
            # Per-IP quota: reject vectors from over-represented sources
            if ip is not None:
                max_allowed = int(self._max_size * self._MAX_PER_IP_FRACTION)
                ip_count = sum(1 for stored_ip in self._ip_buffer if stored_ip == ip)
                if ip_count >= max_allowed:
                    return  # silently drop — log at debug level if needed

            self._buffer.append(features)
            self._ip_buffer.append(ip)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

    def get_training_data(self) -> np.ndarray:
        """Return a copy of the buffer as a 2-D numpy array."""
        with self._lock:
            if not self._buffer:
                return np.empty((0, 0))
            return np.array(list(self._buffer))

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._ip_buffer.clear()


# Module-level singleton
baseline_store = BaselineStore()
