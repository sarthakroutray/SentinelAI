"""Pydantic schemas for IP profile endpoints."""

from datetime import datetime

from pydantic import BaseModel


class IpProfileResponse(BaseModel):
    ip: str
    total_logs: int
    error_ratio: float
    last_seen: datetime
    avg_risk_score: float
    recent_alert_count: int
