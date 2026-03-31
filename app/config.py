"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global settings sourced from env / .env file."""

    DATABASE_URL: str  # e.g. postgresql+asyncpg://user:pass@host:port/dbname
    REDIS_URL: str = "redis://localhost:6379/0"
    APP_NAME: str = "SentinelAI"
    DEBUG: bool = False

    # Rule-engine tunables
    IP_RATE_WINDOW_SECONDS: int = 60
    IP_RATE_THRESHOLD: int = 5

    # Phase 3 – Anomaly detection tunables
    MODEL_RETRAIN_INTERVAL: int = 200
    BASELINE_BUFFER_MAX: int = 2000
    ANOMALY_THRESHOLD_LOW: float = 0.2
    ANOMALY_THRESHOLD_MEDIUM: float = 0.4
    ANOMALY_THRESHOLD_HIGH: float = 0.7
    ISOLATION_CONTAMINATION: float = 0.05
    RULE_WEIGHT: float = 0.5
    STAT_WEIGHT: float = 0.3
    ISO_WEIGHT: float = 0.2
    RETRAIN_COOLDOWN_SECONDS: int = 300

    # Authentication – empty string disables auth (dev mode only)
    API_KEY: str = ""

    # Security – CORS allowed origins (comma-separated in env)
    # Example: CORS_ORIGINS=https://app.example.com,https://admin.example.com
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Queue backpressure – reject ingest requests when queue exceeds this depth
    MAX_QUEUE_DEPTH: int = 50_000

    # Rate limiting for log ingestion (requests per minute per IP)
    RATE_LIMIT_LOGS_PER_MINUTE: int = 300

    # Model store – Redis key TTL for persisted model artifact (0 = no expiry)
    MODEL_ARTIFACT_TTL: int = 0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: str | list) -> list[str]:
        """Accept either a Python list (tests/Python) or a comma-separated string (env)."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return list(v)


settings = Settings()  # type: ignore[call-arg]
