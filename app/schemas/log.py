"""Pydantic schemas for log payloads."""

import ipaddress as _ipaddress
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL", "FATAL"}


class LogCreate(BaseModel):
    """Request body for POST /logs."""

    source: str = Field(..., min_length=1, max_length=255, examples=["firewall"])
    log_level: str = Field(..., min_length=1, max_length=50, examples=["ERROR"])
    message: str = Field(..., min_length=1, examples=["Unauthorized access attempt"])
    timestamp: datetime
    ip_address: str | None = Field(default=None, max_length=45, examples=["192.168.1.100"])

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        if v.upper() not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}"
            )
        return v.upper()

    @field_validator("timestamp")
    @classmethod
    def _validate_timestamp(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        # Ensure v is timezone-aware for comparison
        v_utc = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        if v_utc > now + timedelta(minutes=5):
            raise ValueError("timestamp cannot be more than 5 minutes in the future")
        if v_utc < now - timedelta(days=365):
            raise ValueError("timestamp cannot be more than 1 year in the past")
        return v

    @field_validator("ip_address")
    @classmethod
    def _validate_ip_address(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            _ipaddress.ip_address(v)
        except ValueError:
            raise ValueError(f"Invalid IP address format: {v}")
        return v


class LogResponse(BaseModel):
    """Serialised log returned from the API."""

    id: uuid.UUID
    source: str
    log_level: str
    message: str
    timestamp: datetime
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
