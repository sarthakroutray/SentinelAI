"""SQLAlchemy model – alerts table."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("logs.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # LOW, MEDIUM, HIGH
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.0
    )
    score_breakdown: Mapped[dict] = mapped_column(
        JSON().with_variant(PG_JSONB(), "postgresql"), nullable=False, default=dict
    )
    anomaly_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    log = relationship("Log", lazy="noload")

    __table_args__ = (
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_log_id", "log_id", unique=True),
        Index("ix_alerts_created_at", "created_at"),
        Index("ix_alerts_risk_score", "risk_score"),
        Index("ix_alerts_severity_created_at", "severity", "created_at"),
        CheckConstraint(
            "severity IN ('LOW', 'MEDIUM', 'HIGH')",
            name="ck_alerts_severity",
        ),
    )
