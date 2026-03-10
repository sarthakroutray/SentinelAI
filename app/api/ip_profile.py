"""API router – per-IP profile analytics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.middleware.auth import verify_api_key
from app.models.alert import Alert
from app.models.log import Log
from app.schemas.ip_profile import IpProfileResponse

router = APIRouter(prefix="/ip", tags=["IP Profile"], dependencies=[Depends(verify_api_key)])


@router.get("/{ip}/profile", response_model=IpProfileResponse)
async def get_ip_profile(
    ip: str,
    session: AsyncSession = Depends(get_session),
) -> IpProfileResponse:
    """Return aggregate profile metrics for a single IP address."""
    recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    stmt = (
        select(
            func.count(Log.id).label("total_logs"),
            func.sum(case((Log.log_level.in_(["ERROR", "CRITICAL"]), 1), else_=0)).label("error_logs"),
            func.max(Log.timestamp).label("last_seen"),
            func.coalesce(func.avg(Alert.risk_score), 0.0).label("avg_risk_score"),
            func.sum(case((Alert.created_at >= recent_cutoff, 1), else_=0)).label("recent_alert_count"),
        )
        .select_from(Log)
        .outerjoin(Alert, Alert.log_id == Log.id)
        .where(Log.ip_address == ip)
    )

    row = (await session.execute(stmt)).mappings().one()
    total_logs = int(row["total_logs"] or 0)

    if total_logs == 0:
        raise HTTPException(status_code=404, detail=f"IP profile not found for {ip}")

    error_logs = int(row["error_logs"] or 0)
    last_seen = row["last_seen"]
    if last_seen is None:
        raise HTTPException(status_code=404, detail=f"IP profile not found for {ip}")

    return IpProfileResponse(
        ip=ip,
        total_logs=total_logs,
        error_ratio=round(error_logs / total_logs, 4),
        last_seen=last_seen,
        avg_risk_score=round(float(row["avg_risk_score"] or 0.0), 4),
        recent_alert_count=int(row["recent_alert_count"] or 0),
    )
