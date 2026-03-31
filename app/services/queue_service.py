"""Redis-backed queue service with retry, DLQ, and crash recovery.

Changes from baseline:
- QueueMessage TypedDict documents the internal message structure.
- enqueue() now checks queue depth against MAX_QUEUE_DEPTH and raises
  QueueFullError (HTTP 429) when the high-water mark is reached.
- publish_dashboard_event() swallows Redis errors with a single WARNING
  log rather than propagating exceptions into the worker async task.
- listen_dashboard_events() uses exponential backoff on retry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

from app.redis_pool import get_redis
from app.config import settings

logger = logging.getLogger(__name__)

# Redis key names
MAIN_QUEUE = "sentinel:queue:logs"
PROCESSING_QUEUE = "sentinel:queue:processing"
DLQ = "sentinel:queue:dlq"
WORKER_HEARTBEAT_KEY = "sentinel:worker:heartbeat"
MODEL_RETRAIN_KEY = "sentinel:model:last_retrain"
DASHBOARD_EVENTS_CHANNEL = "sentinel:events:dashboard"
MAX_RETRIES = 3
VISIBILITY_TIMEOUT = 30  # seconds


class QueueFull(Exception):
    """Raised when the Redis queue exceeds MAX_QUEUE_DEPTH."""


class QueueMessage(TypedDict, total=False):
    """Internal structure of a Redis queue message.

    ``total=False`` because not all fields are present in every lifecycle stage.
    """

    payload: dict[str, Any]
    retry_count: int
    enqueued_at: float
    started_processing_at: float
    process_after: float
    moved_to_dlq_at: float
    # Internal sentinel carrying the exact raw JSON for lrem matching
    __raw: str


async def enqueue(payload: dict[str, Any]) -> None:
    """Push a log payload onto the main queue.

    Raises:
        QueueFull: When the queue depth exceeds ``settings.MAX_QUEUE_DEPTH``.
            Callers should translate this to an HTTP 429 response.
    """
    redis = await get_redis()

    # Backpressure guard — prevent unbounded Redis memory growth
    current_depth = await redis.llen(MAIN_QUEUE)
    if current_depth >= settings.MAX_QUEUE_DEPTH:
        raise QueueFull(
            f"Queue depth {current_depth} >= MAX_QUEUE_DEPTH {settings.MAX_QUEUE_DEPTH}. "
            "Rejecting ingest request to protect system stability."
        )

    message = json.dumps({
        "payload": payload,
        "retry_count": 0,
        "enqueued_at": time.time(),
    })
    await redis.lpush(MAIN_QUEUE, message)
    logger.debug("Enqueued log payload onto %s (depth=%d)", MAIN_QUEUE, current_depth + 1)


async def dequeue() -> QueueMessage | None:
    """Atomically move one item from main queue to processing queue.

    Returns the parsed message dict, or None if the queue is empty.
    Uses BLMOVE for atomic move (blocking with 2s timeout).

    Each dequeued message is tagged with ``started_processing_at`` so
    the recovery sweep can distinguish stale items from active ones.
    """
    redis = await get_redis()
    raw = await redis.blmove(
        MAIN_QUEUE, PROCESSING_QUEUE, 2,
        src="RIGHT", dest="LEFT",
    )
    if raw is None:
        return None
    parsed: dict[str, Any] = json.loads(raw)

    # Tag with processing start time and replace entry in processing queue
    parsed["started_processing_at"] = time.time()
    updated_raw = json.dumps({k: v for k, v in parsed.items() if not k.startswith("__")})

    # Atomically replace: remove the original raw entry, push updated one
    pipe = redis.pipeline()
    pipe.lrem(PROCESSING_QUEUE, 1, raw)
    pipe.lpush(PROCESSING_QUEUE, updated_raw)
    await pipe.execute()

    # Preserve the exact bytes for acknowledge/retry_or_dlq matching
    parsed["__raw"] = updated_raw
    return parsed  # type: ignore[return-value]


async def acknowledge(message: QueueMessage) -> None:
    """Remove a successfully processed message from the processing queue."""
    redis = await get_redis()
    raw = message.get("__raw")
    if raw is None:
        raw = json.dumps({k: v for k, v in message.items() if not k.startswith("__")})
    await redis.lrem(PROCESSING_QUEUE, 1, raw)


async def retry_or_dlq(message: QueueMessage) -> bool:
    """Re-enqueue with incremented retry count, or move to DLQ.

    Returns True if requeued, False if moved to DLQ.
    """
    from app.metrics import increment_async

    clean = {k: v for k, v in message.items() if not k.startswith("__")}
    raw_original = message.get("__raw")
    if raw_original is None:
        raw_original = json.dumps({**clean, "retry_count": clean.get("retry_count", 0)})

    clean["retry_count"] = clean.get("retry_count", 0) + 1

    redis = await get_redis()
    await redis.lrem(PROCESSING_QUEUE, 1, raw_original)

    if clean["retry_count"] >= MAX_RETRIES:
        clean["moved_to_dlq_at"] = time.time()
        await redis.lpush(DLQ, json.dumps(clean))
        await increment_async("dlq_count")
        logger.warning("Message moved to DLQ after %d retries", clean["retry_count"])
        return False

    clean["process_after"] = time.time() + (2 ** clean["retry_count"])
    await redis.lpush(MAIN_QUEUE, json.dumps(clean))
    await increment_async("retries")
    logger.info("Message requeued (retry %d/%d)", clean["retry_count"], MAX_RETRIES)
    return True


async def recover_processing_queue() -> int:
    """Move *stale* items from the processing queue back to the main queue.

    Only requeues messages whose ``started_processing_at`` is older than
    ``VISIBILITY_TIMEOUT`` seconds ago.  Called on worker startup.
    Returns the number of recovered messages.
    """
    redis = await get_redis()
    items = await redis.lrange(PROCESSING_QUEUE, 0, -1)
    if not items:
        return 0

    now = time.time()
    count = 0
    for raw in items:
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            await redis.lrem(PROCESSING_QUEUE, 1, raw)
            await redis.lpush(MAIN_QUEUE, raw)
            count += 1
            continue

        started_at = parsed.get("started_processing_at", 0)
        if now - started_at > VISIBILITY_TIMEOUT:
            await redis.lrem(PROCESSING_QUEUE, 1, raw)
            await redis.lpush(MAIN_QUEUE, raw)
            count += 1

    if count:
        logger.info(
            "Recovered %d stale messages from processing queue (visibility_timeout=%ds)",
            count, VISIBILITY_TIMEOUT,
        )
    return count


async def dlq_list() -> list[dict[str, Any]]:
    """Return all items currently in the dead-letter queue."""
    redis = await get_redis()
    items = await redis.lrange(DLQ, 0, -1)
    return [json.loads(item) for item in items]


async def queue_lengths() -> dict[str, int]:
    """Return current lengths of all queues."""
    redis = await get_redis()
    return {
        "main": await redis.llen(MAIN_QUEUE),
        "processing": await redis.llen(PROCESSING_QUEUE),
        "dlq": await redis.llen(DLQ),
    }


async def queue_depth_total() -> int:
    """Return total depth across main, processing, and DLQ queues."""
    redis = await get_redis()
    pipeline = redis.pipeline()
    pipeline.llen(MAIN_QUEUE)
    pipeline.llen(PROCESSING_QUEUE)
    pipeline.llen(DLQ)
    main, processing, dlq = await pipeline.execute()
    return int(main) + int(processing) + int(dlq)


async def set_worker_heartbeat(timestamp: float) -> None:
    """Write worker heartbeat timestamp (epoch seconds)."""
    redis = await get_redis()
    await redis.set(WORKER_HEARTBEAT_KEY, str(timestamp), ex=120)


async def get_worker_heartbeat() -> float | None:
    """Read the latest worker heartbeat timestamp."""
    redis = await get_redis()
    raw = await redis.get(WORKER_HEARTBEAT_KEY)
    return float(raw) if raw is not None else None


async def set_last_model_retrain(iso_timestamp: str) -> None:
    """Persist latest model retrain timestamp in ISO8601."""
    redis = await get_redis()
    await redis.set(MODEL_RETRAIN_KEY, iso_timestamp)


async def get_last_model_retrain() -> str | None:
    """Read latest model retrain timestamp from Redis."""
    redis = await get_redis()
    return await redis.get(MODEL_RETRAIN_KEY)


async def publish_dashboard_event(event: dict[str, Any]) -> None:
    """Publish realtime dashboard event to Redis Pub/Sub.

    Errors are logged as WARNING rather than raised, so a transient Redis
    failure does not propagate as an unhandled worker task exception.
    """
    try:
        redis = await get_redis()
        await redis.publish(DASHBOARD_EVENTS_CHANNEL, json.dumps(event))
    except Exception:
        logger.warning(
            "Failed to publish dashboard event (type=%s) — Redis may be unavailable",
            event.get("type", "unknown"),
            exc_info=True,
        )


async def listen_dashboard_events(
    handler: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Consume dashboard events via async Pub/Sub iterator.

    Uses exponential backoff on retry (max 60 s) to avoid thundering-herd
    reconnection storms after Redis becomes available again.
    """
    retry_attempt = 0
    while True:
        pubsub = None
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(DASHBOARD_EVENTS_CHANNEL)
            retry_attempt = 0  # reset backoff on successful connection

            async for message in pubsub.listen():
                if message.get("type") == "message":
                    raw_data = message.get("data")
                    if isinstance(raw_data, str):
                        await handler(json.loads(raw_data))

        except asyncio.CancelledError:
            raise
        except Exception:
            retry_attempt += 1
            backoff = min(2 ** retry_attempt, 60)
            logger.warning(
                "Dashboard Pub/Sub listener error (attempt %d); retrying in %ds",
                retry_attempt, backoff,
                exc_info=True,
            )
            await asyncio.sleep(backoff)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(DASHBOARD_EVENTS_CHANNEL)
                    await pubsub.aclose()
                except Exception:
                    pass
