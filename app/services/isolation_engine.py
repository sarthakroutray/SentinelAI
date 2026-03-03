"""IsolationForest anomaly scoring engine.

Score range: 0.0 – 1.0

Model trains ONLY on baseline (non-anomalous) data.
Retraining is non-blocking and uses asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import IsolationForest

from app.config import settings
from app.services.baseline_store import baseline_store

logger = logging.getLogger(__name__)


class IsolationEngine:
    """Thin wrapper around sklearn IsolationForest with async retraining."""

    def __init__(self) -> None:
        self._model: IsolationForest | None = None
        self._trained = False
        self._retraining = False
        self._lock = threading.Lock()
        self._contamination = settings.ISOLATION_CONTAMINATION
        self._last_retrain_at: datetime | None = None

    # ── Scoring ──────────────────────────────────────────────────────

    def score(self, features: list[float]) -> float:
        """Return an isolation anomaly score in [0.0, 1.0].

        If the model is not yet trained, returns 0.0.
        """
        with self._lock:
            if not self._trained or self._model is None:
                return 0.0
            arr = np.array([features])
            # decision_function: higher = more normal, lower = more anomalous
            raw = self._model.decision_function(arr)[0]
            # Map raw score to [0, 1.0]: clamp raw to [-0.5, 0.5] then invert
            normalised = max(min(-raw, 0.5), -0.5)  # invert: lower raw → higher anomaly
            scaled = (normalised + 0.5) / 1.0
            return round(min(max(scaled, 0.0), 1.0), 4)

    @property
    def is_trained(self) -> bool:
        with self._lock:
            return self._trained

    @property
    def is_retraining(self) -> bool:
        with self._lock:
            return self._retraining

    # ── Retraining ───────────────────────────────────────────────────

    def should_retrain(self) -> bool:
        """Check if we have enough baseline data and aren't already retraining."""
        with self._lock:
            if self._retraining:
                return False
        return baseline_store.size >= settings.MODEL_RETRAIN_INTERVAL

    async def retrain_async(self) -> None:
        """Retrain in a background thread – non-blocking."""
        with self._lock:
            if self._retraining:
                return
            self._retraining = True

        try:
            data = baseline_store.get_training_data()
            if len(data) < settings.MODEL_RETRAIN_INTERVAL:
                return

            logger.info(
                "IsolationForest retraining started (samples=%d, contamination=%.2f)",
                len(data), self._contamination,
            )

            def _fit():
                model = IsolationForest(
                    contamination=self._contamination,
                    random_state=42,
                    n_estimators=100,
                )
                model.fit(data)
                return model

            new_model = await asyncio.to_thread(_fit)

            with self._lock:
                self._model = new_model
                self._trained = True
                self._last_retrain_at = datetime.now(timezone.utc)

            try:
                from app.services.queue_service import set_last_model_retrain

                await set_last_model_retrain(self._last_retrain_at.isoformat())
            except Exception:
                logger.debug("Failed to persist last model retrain metadata", exc_info=True)

            logger.info("IsolationForest retrained successfully")
        finally:
            with self._lock:
                self._retraining = False

    def reset(self) -> None:
        """Reset engine state (for testing)."""
        with self._lock:
            self._model = None
            self._trained = False
            self._retraining = False
            self._last_retrain_at = None

    @property
    def last_retrain_at(self) -> datetime | None:
        with self._lock:
            return self._last_retrain_at


# Module-level singleton
isolation_engine = IsolationEngine()
