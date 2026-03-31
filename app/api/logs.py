"""API router – log ingestion with rate limiting."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.limiter import limiter
from app.metrics import increment_async
from app.middleware.auth import verify_api_key
from app.schemas.alert import LogWithAlertResponse, LogResponseRef
from app.schemas.log import LogCreate
from app.services.log_service import ingest_log
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["Logs"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=LogWithAlertResponse, status_code=201)
@limiter.limit(lambda: f"{settings.RATE_LIMIT_LOGS_PER_MINUTE}/minute")
async def create_log(
    request: Request,  # required by slowapi
    payload: LogCreate,
    session: AsyncSession = Depends(get_session),
) -> LogWithAlertResponse:
    """Ingest a security log, save it, and enqueue for async alert processing.

    Rate-limited to ``RATE_LIMIT_LOGS_PER_MINUTE`` requests per minute per IP.
    Returns HTTP 429 when the limit is exceeded.
    """
    log = await ingest_log(session, payload)
    await increment_async("logs_received")
    logger.info("Log ingested id=%s, enqueued for alert evaluation", log.id)

    return LogWithAlertResponse(
        log=LogResponseRef.model_validate(log),
        alert=None,  # Alert created asynchronously by the worker
    )
