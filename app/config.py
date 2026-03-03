"""Application configuration loaded from environment variables."""

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()  # type: ignore[call-arg]
