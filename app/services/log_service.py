"""Service layer – log ingestion and queue enqueue."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

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

    Returns the persisted ``Log``.
    """
    log = Log(
        id=uuid.uuid4(),
        source=payload.source,
        log_level=payload.log_level.upper(),
        message=payload.message,
        timestamp=payload.timestamp,
        ip_address=payload.ip_address,
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
        except Exception:
            logger.exception("Failed to enqueue log %s – will be recovered", log.id)
            try:
                from app.metrics import increment_async
                await increment_async("enqueue_failures")
            except Exception:
                pass

    return log
