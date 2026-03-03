"""Tests for the /metrics endpoint and in-memory counters."""

import asyncio
import uuid
from datetime import datetime, timezone

import app.metrics as metrics_mod
from app.models.alert import Alert
from app.models.log import Log


def _insert_alert(async_session_maker, risk_score: float):
    async def _do():
        async with async_session_maker() as session:
            log = Log(
                id=uuid.uuid4(),
                source="metrics-test",
                log_level="ERROR",
                message="test message",
                timestamp=datetime.now(timezone.utc),
                ip_address="127.0.0.1",
                created_at=datetime.now(timezone.utc),
            )
            session.add(log)
            await session.flush()

            alert = Alert(
                id=uuid.uuid4(),
                log_id=log.id,
                severity="HIGH",
                reason="test",
                risk_score=risk_score,
                score_breakdown={"statistical": 0.0},
                anomaly_type="rule_match",
                created_at=datetime.now(timezone.utc),
            )
            session.add(alert)
            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_do())
    finally:
        loop.close()


def test_metrics_endpoint_returns_counters(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    body = response.json()
    assert "logs_received" in body
    assert "alerts_created" in body
    assert "retries" in body
    assert "dlq_count" in body
    assert "high_risk_count" in body
    assert "medium_risk_count" in body
    assert "low_risk_count" in body


def test_metrics_endpoint_severity_distribution(client, async_session_maker):
    _insert_alert(async_session_maker, 0.9)
    _insert_alert(async_session_maker, 0.7)
    _insert_alert(async_session_maker, 0.5)
    _insert_alert(async_session_maker, 0.4)
    _insert_alert(async_session_maker, 0.39)

    response = client.get("/metrics")
    assert response.status_code == 200

    body = response.json()
    assert body["high_risk_count"] == 2
    assert body["medium_risk_count"] == 2
    assert body["low_risk_count"] == 1


def test_metrics_increment():
    metrics_mod.increment("logs_received")
    metrics_mod.increment("logs_received")
    metrics_mod.increment("alerts_created", 3)

    assert metrics_mod.get("logs_received") == 2
    assert metrics_mod.get("alerts_created") == 3


def test_metrics_snapshot():
    metrics_mod.increment("retries")
    snap = metrics_mod.snapshot()
    assert isinstance(snap, dict)
    assert snap["retries"] == 1


def test_metrics_timeseries_shape(client, async_session_maker):
    _insert_alert(async_session_maker, 0.8)
    _insert_alert(async_session_maker, 0.3)

    response = client.get("/metrics/timeseries", params={"window": 15})
    assert response.status_code == 200

    body = response.json()
    assert len(body["timestamps"]) == 15
    assert len(body["logs"]) == 15
    assert len(body["alerts"]) == 15
    assert sum(body["alerts"]) >= 2


def test_health_endpoint_extended_fields(client):
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["db_latency_ms"], (int, float))
    assert isinstance(body["worker_alive"], bool)
    assert isinstance(body["queue_depth"], int)
    assert (body["last_model_retrain"] is None) or isinstance(body["last_model_retrain"], str)
