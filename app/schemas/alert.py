"""Pydantic schemas for alert payloads."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AlertResponse(BaseModel):
    """Serialised alert returned from the API."""

    id: uuid.UUID
    log_id: uuid.UUID
    severity: Severity
    reason: str
    risk_score: float = 0.0
    score_breakdown: dict = {}
    anomaly_type: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    # Pre-migration rows may have NULL in these columns; coerce to safe defaults.
    @field_validator("risk_score", mode="before")
    @classmethod
    def _coerce_risk_score(cls, v: object) -> float:
        return float(v) if v is not None else 0.0

    @field_validator("score_breakdown", mode="before")
    @classmethod
    def _coerce_score_breakdown(cls, v: object) -> dict:
        return v if isinstance(v, dict) else {}


class AlertListResponse(BaseModel):
    """Paginated alert list response."""

    total: int
    limit: int
    offset: int
    items: list[AlertResponse]


class LogWithAlertResponse(BaseModel):
    """Combined response after ingesting a log."""

    log: "LogResponseRef"
    alert: AlertResponse | None = None


# Lightweight forward-reference to avoid circular import
class LogResponseRef(BaseModel):
    id: uuid.UUID
    source: str
    log_level: str
    message: str
    timestamp: datetime
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# Rebuild to resolve forward refs
LogWithAlertResponse.model_rebuild()
