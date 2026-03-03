"""Pydantic schemas for health endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    db_latency_ms: float
    worker_alive: bool
    queue_depth: int
    last_model_retrain: datetime | None
