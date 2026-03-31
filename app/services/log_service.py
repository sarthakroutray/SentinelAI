"""Service layer – log ingestion and queue enqueue."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import Log
from app.schemas.log import LogCreate

logger = logging.getLogger(__name__)

# Optional Redis enqueue – imported lazily so tests can run without Redis
_enqueue = None


def _get_enqueue():
    global _enqueue
    if _enqueue is None:
        try:
            from app.services.queue_service import enqueue
            _enqueue = enqueue
        except Exception:
            _enqueue = None
    return _enqueue


async def ingest_log(session: AsyncSession, payload: LogCreate) -> Log:
    """Persist a log entry and enqueue it for asynchronous alert evaluation.

    The ``enqueued`` flag tracks whether the log was successfully pushed
    to the Redis queue.  Logs that fail enqueue (``enqueued=False``) are
    swept up by the worker on startup so no log goes unprocessed.

    Raises:
        HTTPException(429): When the Redis queue exceeds MAX_QUEUE_DEPTH so
            the caller (API layer) can return an appropriate backpressure response.

    Returns the persisted ``Log``.
    """
    log = Log(
        id=uuid.uuid4(),
        source=payload.source,
        log_level=payload.log_level.upper(),
        message=payload.message,
        timestamp=payload.timestamp,
        ip_address=payload.ip_address,
        enqueued=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)

    # Enqueue for the alert worker (best-effort; at-least-once via Redis)
    enqueue_fn = _get_enqueue()
    if enqueue_fn is not None:
        try:
            await enqueue_fn({
                "log_id": str(log.id),
                "log_level": log.log_level,
                "message": log.message,
                "ip_address": log.ip_address,
            })
            log.enqueued = True
            await session.commit()
        except Exception as exc:
            # Re-raise queue-full errors so the API layer returns HTTP 429
            from app.services.queue_service import QueueFull
            if isinstance(exc, QueueFull):
                # Roll back the committed log row so ingest is truly rejected
                await session.delete(log)
                await session.commit()
                raise HTTPException(
                    status_code=429,
                    detail="Queue is full. Retry after the backlog clears.",
                ) from exc

            logger.exception(
                "Failed to enqueue log %s – will be recovered by worker sweep", log.id
            )
            try:
                from app.metrics import increment_async
                await increment_async("enqueue_failures")
            except Exception:
                pass

    return log
