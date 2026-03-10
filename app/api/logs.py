"""API router – log ingestion."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.metrics import increment_async
from app.middleware.auth import verify_api_key
from app.schemas.alert import LogWithAlertResponse, LogResponseRef
from app.schemas.log import LogCreate
from app.services.log_service import ingest_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["Logs"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=LogWithAlertResponse, status_code=201)
async def create_log(
    payload: LogCreate,
    session: AsyncSession = Depends(get_session),
) -> LogWithAlertResponse:
    """Ingest a security log, save it, and enqueue for async alert processing."""
    log = await ingest_log(session, payload)
    await increment_async("logs_received")
    logger.info("Log ingested id=%s, enqueued for alert evaluation", log.id)

    return LogWithAlertResponse(
        log=LogResponseRef.model_validate(log),
        alert=None,  # Alert created asynchronously by the worker
    )
