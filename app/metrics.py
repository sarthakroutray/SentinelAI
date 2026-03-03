"""In-memory metrics counters and /metrics endpoint."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.alert import Alert
from app.models.log import Log
from app.schemas.metrics import MetricsResponse, MetricsTimeseriesResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Observability"])

_lock = threading.Lock()
_counters: dict[str, int] = {
    "logs_received": 0,
    "alerts_created": 0,
    "retries": 0,
    "dlq_count": 0,
    "enqueue_failures": 0,
}

_REDIS_METRIC_PREFIX = "sentinel:metrics:"
_COUNTER_KEYS = ("logs_received", "alerts_created", "retries", "dlq_count", "enqueue_failures")


def increment(name: str, amount: int = 1) -> None:
    """Thread-safe counter increment."""
    with _lock:
        _counters[name] = _counters.get(name, 0) + amount


def get(name: str) -> int:
    with _lock:
        return _counters.get(name, 0)


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counters)


# ── Redis-backed async counters (cross-process) ─────────────────────


async def increment_async(name: str, amount: int = 1) -> None:
    """Increment a counter in both in-memory store and Redis.

    The in-memory update keeps the sync ``get`` / ``snapshot`` functions
    working for tests while Redis makes the counter visible across the
    API and worker processes.
    """
    increment(name, amount)
    try:
        from app.redis_pool import get_redis

        redis = await get_redis()
        await redis.incrby(f"{_REDIS_METRIC_PREFIX}{name}", amount)
    except Exception:
        logger.debug("Redis counter increment failed for %s", name, exc_info=True)


async def snapshot_async() -> dict[str, int]:
    """Read counters from Redis (cross-process accurate).

    Falls back to the in-memory snapshot when Redis is unavailable.
    """
    try:
        from app.redis_pool import get_redis

        redis = await get_redis()
        pipe = redis.pipeline()
        for key in _COUNTER_KEYS:
            pipe.get(f"{_REDIS_METRIC_PREFIX}{key}")
        values = await pipe.execute()
        return {
            key: int(val) if val else 0
            for key, val in zip(_COUNTER_KEYS, values)
        }
    except Exception:
        logger.debug("Redis counter read failed, falling back to in-memory", exc_info=True)
        return snapshot()


# ── Metrics response cache (M-2: avoid repeated full-table scan) ────

_metrics_cache: MetricsResponse | None = None
_metrics_cache_at: float = 0.0
_METRICS_CACHE_TTL = 4.0  # seconds
_metrics_cache_lock: asyncio.Lock | None = None


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(session: AsyncSession = Depends(get_session)) -> MetricsResponse:
    """Return current in-memory metric counters + risk bucket distribution."""
    return await compute_metrics_response(session)


async def compute_metrics_response(session: AsyncSession) -> MetricsResponse:
    """Compute current metrics snapshot with DB-backed severity distribution.

    Results are cached for a few seconds to avoid repeated full-table
    aggregate scans when the broadcast loop and /metrics endpoint both
    call this concurrently.
    """
    global _metrics_cache, _metrics_cache_at, _metrics_cache_lock

    if _metrics_cache_lock is None:
        _metrics_cache_lock = asyncio.Lock()

    now = time.monotonic()
    if _metrics_cache is not None and (now - _metrics_cache_at) < _METRICS_CACHE_TTL:
        return _metrics_cache

    async with _metrics_cache_lock:
        # Re-check after acquiring lock (double-checked locking pattern)
        now = time.monotonic()
        if _metrics_cache is not None and (now - _metrics_cache_at) < _METRICS_CACHE_TTL:
            return _metrics_cache

        severity_stmt = select(
            func.coalesce(
                func.sum(case((Alert.risk_score >= 0.7, 1), else_=0)), 0
            ).label("high_risk_count"),
            func.coalesce(
                func.sum(
                    case(
                        ((Alert.risk_score >= 0.4) & (Alert.risk_score < 0.7), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("medium_risk_count"),
            func.coalesce(
                func.sum(case((Alert.risk_score < 0.4, 1), else_=0)),
                0,
            ).label("low_risk_count"),
        )
        result = await session.execute(severity_stmt)
        severity_counts = result.mappings().one()

        counters = await snapshot_async()
        response = MetricsResponse(
            logs_received=counters.get("logs_received", 0),
            alerts_created=counters.get("alerts_created", 0),
            retries=counters.get("retries", 0),
            dlq_count=counters.get("dlq_count", 0),
            enqueue_failures=counters.get("enqueue_failures", 0),
            high_risk_count=int(severity_counts["high_risk_count"]),
            medium_risk_count=int(severity_counts["medium_risk_count"]),
            low_risk_count=int(severity_counts["low_risk_count"]),
        )

        _metrics_cache = response
        _metrics_cache_at = now
        return response


@router.get("/metrics/timeseries", response_model=MetricsTimeseriesResponse)
async def metrics_timeseries(
    window: int = 15,
    session: AsyncSession = Depends(get_session),
) -> MetricsTimeseriesResponse:
    """Return logs/alerts per minute for the last N minutes."""
    window = max(1, min(window, 180))

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(minutes=window - 1)

    log_bucket = func.date_trunc("minute", Log.created_at)
    alert_bucket = func.date_trunc("minute", Alert.created_at)

    log_stmt = (
        select(log_bucket.label("bucket"), func.count(Log.id).label("count"))
        .where(Log.created_at >= start)
        .group_by(log_bucket)
        .order_by(log_bucket)
    )
    alert_stmt = (
        select(alert_bucket.label("bucket"), func.count(Alert.id).label("count"))
        .where(Alert.created_at >= start)
        .group_by(alert_bucket)
        .order_by(alert_bucket)
    )

    log_rows = (await session.execute(log_stmt)).all()
    alert_rows = (await session.execute(alert_stmt)).all()

    log_map = {_normalise_bucket(row[0]): int(row[1]) for row in log_rows}
    alert_map = {_normalise_bucket(row[0]): int(row[1]) for row in alert_rows}

    timestamps: list[str] = []
    logs: list[int] = []
    alerts: list[int] = []
    for minute_offset in range(window):
        minute = start + timedelta(minutes=minute_offset)
        key = minute.replace(second=0, microsecond=0)
        timestamps.append(key.isoformat())
        logs.append(log_map.get(key, 0))
        alerts.append(alert_map.get(key, 0))

    return MetricsTimeseriesResponse(timestamps=timestamps, logs=logs, alerts=alerts)


def _normalise_bucket(value: object) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value)
    else:
        raise ValueError(f"Unexpected bucket value type: {type(value)!r}")

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
