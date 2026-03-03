"""Pydantic schemas for observability metrics."""

from pydantic import BaseModel


class MetricsResponse(BaseModel):
    logs_received: int
    alerts_created: int
    retries: int
    dlq_count: int
    enqueue_failures: int = 0
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int


class MetricsTimeseriesResponse(BaseModel):
    timestamps: list[str]
    logs: list[int]
    alerts: list[int]
