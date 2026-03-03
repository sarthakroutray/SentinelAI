"""Contamination-safe baseline buffer for IsolationForest training.

Only stores feature vectors from low-risk, non-anomalous logs.
Thread-safe sliding window with configurable max size.
"""

from __future__ import annotations

import threading
from collections import deque

import numpy as np

from app.config import settings


class BaselineStore:
    """In-memory ring buffer of known-good feature vectors."""

    def __init__(self, max_size: int | None = None) -> None:
        self._max_size = max_size or settings.BASELINE_BUFFER_MAX
        self._buffer: deque[list[float]] = deque(maxlen=self._max_size)
        self._lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────

    def add(self, features: list[float]) -> None:
        """Append a feature vector to the baseline (thread-safe)."""
        with self._lock:
            self._buffer.append(features)

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


# Module-level singleton
baseline_store = BaselineStore()
