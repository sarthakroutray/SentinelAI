"""API router – alerts retrieval."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.alert import Alert
from app.schemas.alert import AlertListResponse, AlertResponse, Severity

router = APIRouter(prefix="/alerts", tags=["Alerts"])

AlertSort = Literal[
    "timestamp_desc",
    "timestamp_asc",
    "risk_score_desc",
    "risk_score_asc",
]

SORT_MAPPING = {
    "timestamp_desc": Alert.created_at.desc(),
    "timestamp_asc": Alert.created_at.asc(),
    "risk_score_desc": Alert.risk_score.desc(),
    "risk_score_asc": Alert.risk_score.asc(),
}


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    severity: Severity | None = Query(default=None, description="Filter by severity"),
    limit: int = Query(default=50, ge=1, le=200, description="Page size (max 200)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    sort: AlertSort = Query(default="timestamp_desc", description="Sort order"),
    session: AsyncSession = Depends(get_session),
) -> AlertListResponse:
    """Return alerts with optional severity filter, pagination, and sorting."""
    filters = []
    if severity is not None:
        filters.append(Alert.severity == severity.value)

    count_stmt = select(func.count()).select_from(Alert).where(*filters)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(Alert)
        .where(*filters)
        .order_by(SORT_MAPPING[sort])
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    alerts = result.scalars().all()
    return AlertListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[AlertResponse.model_validate(a) for a in alerts],
    )
