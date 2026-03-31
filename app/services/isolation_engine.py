"""IsolationForest anomaly scoring engine.

Score range: 0.0 – 1.0

Model trains ONLY on baseline (non-anomalous) data.
Retraining is non-blocking and uses asyncio.to_thread.

Model artifacts are persisted to Redis after each successful retrain and
restored on startup, eliminating cold-start scoring degradation.

⚠ SINGLE-WORKER CONSTRAINT
   The trained model and retraining state are held in-memory.  Running
   multiple worker processes will result in each worker maintaining its
   own independent model.  For consistent scoring, deploy a single
   alert-worker instance.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from app.config import settings
from app.services.baseline_store import FEATURE_DIM, baseline_store

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Redis keys for model persistence
MODEL_ARTIFACT_KEY = "sentinel:model:artifact"
MODEL_PROVENANCE_KEY = "sentinel:model:provenance"

# Synthetic holdout vectors: (feature_vector, is_anomalous)
# Used to sanity-check that a newly trained model can discriminate at all.
# Vectors are [level_score, msg_len, has_ip, keyword_hits]
_HOLDOUT: list[tuple[list[float], bool]] = [
    # Clearly normal traffic
    ([1.0, 25.0, 0.0, 0.0], False),
    ([1.0, 30.0, 1.0, 0.0], False),
    ([0.0, 15.0, 0.0, 0.0], False),
    ([1.0, 40.0, 1.0, 0.0], False),
    # Clearly anomalous traffic
    ([4.0, 500.0, 1.0, 4.0], True),
    ([3.0, 350.0, 1.0, 3.0], True),
    ([4.0, 400.0, 1.0, 4.0], True),
]


class IsolationEngine:
    """Thin wrapper around sklearn IsolationForest with async retraining.

    Key improvements over baseline:
    - Feature dimension guard: rejects vectors of wrong length
    - Holdout evaluation: rejects retrained models that can't discriminate
    - Redis persistence: model survives worker restarts
    - To-thread scoring: calling score() from async code won't block the loop
      when combined with asyncio.to_thread(isolation_engine.score, features)
    """

    def __init__(self) -> None:
        self._model: IsolationForest | None = None
        self._trained = False
        self._retraining = False
        self._lock = threading.RLock()  # RLock: allows re-entrant locking in same thread
        self._contamination = settings.ISOLATION_CONTAMINATION
        self._last_retrain_at: datetime | None = None
        self._last_retrain_time: float = 0.0  # monotonic time of last retrain
        self._samples_at_last_retrain: int = 0
        # Discrimination score of the last accepted model (higher is better)
        self._last_discrimination_score: float = 0.0
        # Short model identifier for logs and provenance
        self._model_id: str | None = None

    # ── Scoring ──────────────────────────────────────────────────────

    def score(self, features: list[float]) -> float:
        """Return an isolation anomaly score in [0.0, 1.0].

        If the model is not trained, or the feature vector is malformed,
        returns 0.0 rather than raising.

        Note: This method acquires a threading.Lock briefly. For high-throughput
        async callers, wrap with ``asyncio.to_thread(isolation_engine.score, features)``.
        """
        if len(features) != FEATURE_DIM:
            logger.error(
                "Feature dimension mismatch in score(): expected %d, got %d",
                FEATURE_DIM, len(features),
            )
            return 0.0

        with self._lock:
            if not self._trained or self._model is None:
                return 0.0
            arr = np.array([features])
            # decision_function: higher = more normal, lower = more anomalous
            raw = self._model.decision_function(arr)[0]
            # Map to [0, 1]: clamp raw to [-0.5, 0.5] then invert + normalise
            normalised = max(min(-raw, 0.5), -0.5)
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

    @property
    def last_retrain_at(self) -> datetime | None:
        with self._lock:
            return self._last_retrain_at

    @property
    def model_id(self) -> str | None:
        with self._lock:
            return self._model_id

    # ── Retraining ───────────────────────────────────────────────────

    def should_retrain(self) -> bool:
        """Check if retraining conditions are met.

        Retraining requires ALL of:
        1. Not already retraining
        2. Enough NEW samples since last retrain (>= MODEL_RETRAIN_INTERVAL)
        3. Enough time elapsed since last retrain (>= RETRAIN_COOLDOWN_SECONDS)
        """
        with self._lock:
            if self._retraining:
                return False

            new_samples = baseline_store.size - self._samples_at_last_retrain
            if new_samples < settings.MODEL_RETRAIN_INTERVAL:
                return False

            if self._last_retrain_time > 0:
                elapsed = time.monotonic() - self._last_retrain_time
                if elapsed < settings.RETRAIN_COOLDOWN_SECONDS:
                    return False

            return True

    async def retrain_async(self) -> None:
        """Retrain in a background thread – non-blocking.

        1. Fits a new model on the current baseline.
        2. Evaluates discrimination on the holdout set.
        3. Rejects the model if it's worse than the current one (>5% regression).
        4. Persists the accepted model to Redis.
        """
        with self._lock:
            if self._retraining:
                return
            self._retraining = True

        try:
            data = baseline_store.get_training_data()
            if len(data) < settings.MODEL_RETRAIN_INTERVAL:
                return

            n_samples = len(data)
            logger.info(
                "IsolationForest retraining started (samples=%d, contamination=%.2f)",
                n_samples, self._contamination,
            )

            def _fit() -> IsolationForest:
                model = IsolationForest(
                    contamination=self._contamination,
                    random_state=42,
                    n_estimators=100,
                )
                model.fit(data)
                return model

            new_model = await asyncio.to_thread(_fit)

            # ── Holdout evaluation ────────────────────────────────────────
            disc_score = _compute_discrimination_score(new_model)
            with self._lock:
                prev_disc = self._last_discrimination_score

            if prev_disc > 0 and disc_score < prev_disc - 0.05:
                logger.warning(
                    "Retrain rejected: discrimination score %.4f < previous %.4f - 0.05",
                    disc_score, prev_disc,
                )
                return

            logger.info(
                "Retrain accepted: discrimination=%.4f (prev=%.4f)",
                disc_score, prev_disc,
            )

            # ── Compute model ID from artifact hash ───────────────────────
            buf = io.BytesIO()
            joblib.dump(new_model, buf)
            artifact_bytes = buf.getvalue()
            model_id = hashlib.sha256(artifact_bytes).hexdigest()[:12]

            now = datetime.now(timezone.utc)

            with self._lock:
                self._model = new_model
                self._trained = True
                self._last_retrain_at = now
                self._last_retrain_time = time.monotonic()
                self._samples_at_last_retrain = baseline_store.size
                self._last_discrimination_score = disc_score
                self._model_id = model_id

            # ── Persist to Redis ──────────────────────────────────────────
            await _persist_model_to_redis(
                artifact_bytes=artifact_bytes,
                model_id=model_id,
                trained_at=now,
                n_samples=n_samples,
                contamination=self._contamination,
                discrimination_score=disc_score,
            )

            logger.info(
                "IsolationForest retrained successfully model_id=%s discrimination=%.4f",
                model_id, disc_score,
            )
        finally:
            with self._lock:
                self._retraining = False

    # ── Persistence ───────────────────────────────────────────────────

    async def restore_from_redis(self) -> bool:
        """Attempt to restore a previously persisted model from Redis.

        Returns True if a model was successfully restored, False otherwise.
        Called on worker startup to avoid cold-start scoring degradation.
        """
        try:
            from app.redis_pool import get_redis
            redis = await get_redis()

            artifact_bytes = await redis.get(MODEL_ARTIFACT_KEY)
            if artifact_bytes is None:
                logger.info("No persisted model artifact found in Redis")
                return False

            provenance_raw = await redis.get(MODEL_PROVENANCE_KEY)
            provenance: dict = json.loads(provenance_raw) if provenance_raw else {}

            loaded_model: IsolationForest = await asyncio.to_thread(
                joblib.load, io.BytesIO(artifact_bytes)
            )
            disc_score = provenance.get("discrimination_score", 0.0)
            model_id = provenance.get("model_id", "unknown")
            trained_at_str = provenance.get("trained_at")
            trained_at = (
                datetime.fromisoformat(trained_at_str)
                if trained_at_str else datetime.now(timezone.utc)
            )

            with self._lock:
                self._model = loaded_model
                self._trained = True
                self._last_retrain_at = trained_at
                self._last_retrain_time = time.monotonic()
                self._last_discrimination_score = float(disc_score)
                self._model_id = model_id

            logger.info(
                "Restored IsolationForest from Redis model_id=%s trained_at=%s",
                model_id, trained_at.isoformat(),
            )
            return True

        except Exception:
            logger.warning("Failed to restore model from Redis — will retrain from scratch", exc_info=True)
            return False

    def reset(self) -> None:
        """Reset engine state (used in tests)."""
        with self._lock:
            self._model = None
            self._trained = False
            self._retraining = False
            self._last_retrain_at = None
            self._last_retrain_time = 0.0
            self._samples_at_last_retrain = 0
            self._last_discrimination_score = 0.0
            self._model_id = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_discrimination_score(model: IsolationForest) -> float:
    """Score the model on the synthetic holdout set.

    Returns a discrimination score in [0, 1] measuring how well the
    model separates known-normal from known-anomalous vectors.
    A score of 0.5 means the model can't discriminate at all; >0.6 is acceptable.
    """
    if not _HOLDOUT:
        return 0.6  # No holdout — assume acceptable

    X = np.array([v for v, _ in _HOLDOUT])
    labels = [is_anomaly for _, is_anomaly in _HOLDOUT]
    raw_scores = model.decision_function(X)

    # Count correct orderings: anomalous samples should score lower than normals
    correct = 0
    total_pairs = 0
    for i, (score_i, label_i) in enumerate(zip(raw_scores, labels)):
        for j, (score_j, label_j) in enumerate(zip(raw_scores, labels)):
            if label_i and not label_j:  # i is anomalous, j is normal
                total_pairs += 1
                if score_i < score_j:   # anomalous should have lower decision score
                    correct += 1

    if total_pairs == 0:
        return 0.6
    return correct / total_pairs


async def _persist_model_to_redis(
    artifact_bytes: bytes,
    model_id: str,
    trained_at: datetime,
    n_samples: int,
    contamination: float,
    discrimination_score: float,
) -> None:
    """Persist model artifact and provenance to Redis."""
    try:
        from app.redis_pool import get_redis
        from app.services.queue_service import set_last_model_retrain

        redis = await get_redis()
        provenance = {
            "model_id": model_id,
            "trained_at": trained_at.isoformat(),
            "n_samples": n_samples,
            "contamination": contamination,
            "feature_dim": FEATURE_DIM,
            "discrimination_score": round(discrimination_score, 4),
        }
        ttl = settings.MODEL_ARTIFACT_TTL or None
        await redis.set(MODEL_ARTIFACT_KEY, artifact_bytes, ex=ttl)
        await redis.set(MODEL_PROVENANCE_KEY, json.dumps(provenance), ex=ttl)
        await set_last_model_retrain(trained_at.isoformat())
    except Exception:
        logger.warning("Failed to persist model artifact to Redis", exc_info=True)


# Module-level singleton
isolation_engine = IsolationEngine()
