"""Alert worker – processes log payloads from the Redis queue.

Phase 3: Hybrid anomaly detection with contamination-safe retraining.
Run via:  python -m app.workers.alert_worker

⚠ SINGLE-WORKER CONSTRAINT
   Detection engines (profile_store, baseline_store, isolation model,
   rule-engine burst tracker) maintain state in-memory.  Running multiple
   worker processes will produce non-deterministic scoring because each
   process holds an independent copy of these stores.  Deploy a **single
   alert-worker instance** for consistent behaviour.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import signal
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.logging_config import setup_logging
from app.metrics import increment_async
from app.models.alert import Alert
from app.models.log import Log
from app.schemas.alert import AlertResponse
from app.services.baseline_store import baseline_store
from app.services.isolation_engine import isolation_engine
from app.services.queue_service import (
    acknowledge,
    dequeue,
    enqueue,
    publish_dashboard_event,
    set_worker_heartbeat,
    recover_processing_queue,
    retry_or_dlq,
)
from app.services.rule_engine import evaluate as rule_evaluate
from app.services.scoring_engine import compute as score_compute
from app.services.statistical_engine import extract_features, score as stat_score

logger = logging.getLogger(__name__)

_shutdown = asyncio.Event()


def _signal_handler() -> None:
    logger.info("Shutdown signal received")
    _shutdown.set()


def _log_task_exception(task: asyncio.Task) -> None:
    """Callback for fire-and-forget tasks so exceptions are surfaced."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background task %s failed: %s", task.get_name(), exc, exc_info=exc)


async def _heartbeat_loop(interval_seconds: float = 5.0) -> None:
    """Continuously publish worker heartbeat while process is running."""
    while not _shutdown.is_set():
        try:
            await set_worker_heartbeat(time.time())
        except Exception:
            logger.debug("Unable to publish worker heartbeat", exc_info=True)

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


async def _sweep_unenqueued_logs() -> int:
    """Re-enqueue logs that were persisted but never reached Redis.

    This covers the case where ``ingest_log`` committed the log row but
    the subsequent Redis ``enqueue`` call failed (``enqueued=False``).
    Called once on worker startup.
    """
    count = 0
    async with async_session() as session:
        stmt = select(Log).where(Log.enqueued == False)  # noqa: E712
        result = await session.execute(stmt)
        logs = result.scalars().all()

        for log in logs:
            try:
                await enqueue({
                    "log_id": str(log.id),
                    "log_level": log.log_level,
                    "message": log.message,
                    "ip_address": log.ip_address,
                })
                log.enqueued = True
                count += 1
            except Exception:
                logger.warning("Failed to re-enqueue log %s during sweep", log.id)

        if count:
            await session.commit()
            logger.info("Sweep: re-enqueued %d previously failed logs", count)

    return count


async def _process_message(message: dict) -> None:
    """Evaluate rules + anomaly scoring for one log payload."""
    payload = message["payload"]
    log_id = payload.get("log_id")

    if not log_id:
        logger.error("Message missing log_id, sending to DLQ")
        await retry_or_dlq(message)
        return

    # Check backoff
    process_after = message.get("process_after", 0)
    now = time.time()
    if process_after > now:
        await asyncio.sleep(min(process_after - now, 5))

    session: AsyncSession
    async with async_session() as session:
        # Verify the log exists
        log = await session.get(Log, uuid.UUID(log_id))
        if log is None:
            logger.error("Log %s not found, sending to DLQ", log_id)
            await retry_or_dlq(message)
            return

        # Idempotency check – skip if alert already exists for this log_id
        existing = await session.execute(
            select(Alert).where(Alert.log_id == uuid.UUID(log_id))
        )
        if existing.scalars().first() is not None:
            logger.info("Alert for log %s already exists, skipping", log_id)
            await acknowledge(message)
            return

        # ── Step 1: Rule engine ──────────────────────────────────────
        rule_result = rule_evaluate(
            log_level=log.log_level,
            message=log.message,
            ip_address=log.ip_address,
        )
        rule_triggered = rule_result is not None

        # ── Step 2: Statistical scoring ──────────────────────────────
        statistical_score = stat_score(
            log_level=log.log_level,
            ip_address=log.ip_address,
        )

        # ── Step 3: Isolation scoring ────────────────────────────────
        features = extract_features(
            log_level=log.log_level,
            message=log.message,
            ip_address=log.ip_address,
        )
        isolation_score = isolation_engine.score(features)

        # ── Step 4: Combined risk scoring ────────────────────────────
        score_result = score_compute(
            statistical_score=statistical_score,
            isolation_score=isolation_score,
            rule_triggered=rule_triggered,
            rule_severity=rule_result.severity if rule_result else None,
        )

        # ── Step 5: Build reason string ──────────────────────────────
        if rule_result is not None:
            reason = rule_result.reason
        elif score_result.severity != "NONE":
            reason = f"Anomaly detected: {score_result.anomaly_type} (risk={score_result.risk_score:.3f})"
        else:
            reason = "No anomaly"

        # ── Step 6: Create alert if risk >= LOW threshold ────────────
        if score_result.severity != "NONE":
            alert = Alert(
                id=uuid.uuid4(),
                log_id=log.id,
                severity=score_result.severity,
                reason=reason,
                risk_score=score_result.risk_score,
                score_breakdown=score_result.breakdown,
                anomaly_type=score_result.anomaly_type,
                created_at=datetime.now(timezone.utc),
            )
            session.add(alert)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.info("Duplicate alert for log %s (concurrent insert), skipping", log_id)
                await acknowledge(message)
                return
            await increment_async("alerts_created")
            alert_payload = AlertResponse.model_validate(alert).model_dump(mode="json")
            task = asyncio.create_task(
                publish_dashboard_event({"type": "alert", "payload": alert_payload})
            )
            task.add_done_callback(_log_task_exception)
            logger.info(
                "Alert created: severity=%s risk=%.3f type=%s log_id=%s",
                score_result.severity, score_result.risk_score,
                score_result.anomaly_type, log_id,
            )
        else:
            logger.info("No alert for log %s (risk=%.3f)", log_id, score_result.risk_score)

        # ── Step 7: Contamination guard – baseline only for safe logs ─
        if not rule_triggered and score_result.risk_score < settings.ANOMALY_THRESHOLD_LOW:
            baseline_store.add(features)

        # ── Step 8: Trigger retraining if threshold met ──────────────
        if isolation_engine.should_retrain():
            retrain_task = asyncio.create_task(isolation_engine.retrain_async())
            retrain_task.add_done_callback(_log_task_exception)

    await acknowledge(message)


async def run() -> None:
    """Main worker loop."""
    setup_logging()
    logger.info("Alert worker starting (redis=%s)", settings.REDIS_URL)

    # Register signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler; use threadsafe callback
            signal.signal(sig, lambda s, f: loop.call_soon_threadsafe(_shutdown.set))

    # Crash recovery: move orphaned processing-queue items back
    recovered = await recover_processing_queue()
    if recovered:
        logger.info("Recovered %d orphaned messages", recovered)

    # Sweep for logs that were persisted but never enqueued to Redis
    swept = await _sweep_unenqueued_logs()
    if swept:
        logger.info("Swept %d un-enqueued logs", swept)

    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    logger.info("Worker ready, polling queue...")

    try:
        while not _shutdown.is_set():
            try:
                message = await dequeue()
                if message is None:
                    continue
                try:
                    await _process_message(message)
                except Exception:
                    logger.exception("Error processing message, moving to retry/DLQ")
                    try:
                        await retry_or_dlq(message)
                    except Exception:
                        logger.exception("Failed to retry/DLQ message")
            except Exception:
                logger.exception("Unhandled error in worker loop")
                await asyncio.sleep(1)
    finally:
        heartbeat_task.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat_task

    logger.info("Worker shut down gracefully")


if __name__ == "__main__":
    asyncio.run(run())

