"""API router – health diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.middleware.auth import verify_api_key
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"], dependencies=[Depends(verify_api_key)])


@router.get("/health", response_model=HealthResponse)
async def health_check(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    """Liveness + operational health diagnostics."""
    db_start = perf_counter()
    await session.execute(text("SELECT 1"))
    db_latency_ms = round((perf_counter() - db_start) * 1000, 2)

    worker_alive = False
    queue_depth = 0
    last_model_retrain = None

    try:
        from app.services.queue_service import (
            get_last_model_retrain,
            get_worker_heartbeat,
            queue_depth_total,
        )

        heartbeat = await get_worker_heartbeat()
        if heartbeat is not None:
            worker_alive = (datetime.now(timezone.utc).timestamp() - heartbeat) <= 30

        queue_depth = await queue_depth_total()
        retrain_iso = await get_last_model_retrain()
        if retrain_iso:
            last_model_retrain = datetime.fromisoformat(retrain_iso)
    except Exception:
        worker_alive = False
        queue_depth = 0

    return HealthResponse(
        status="ok",
        db_latency_ms=db_latency_ms,
        worker_alive=worker_alive,
        queue_depth=queue_depth,
        last_model_retrain=last_model_retrain,
    )
