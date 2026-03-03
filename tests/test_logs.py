import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.alert import Alert
from app.models.log import Log


def test_post_logs_creates_log_and_enqueues(client):
    """POST /logs persists the log and returns it; alert is None (async)."""
    payload = {
        "source": "auth-service",
        "log_level": "ERROR",
        "message": "Database timeout",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_address": "10.0.0.10",
    }

    response = client.post("/logs", json=payload)

    assert response.status_code == 201
    body = response.json()

    assert "log" in body
    assert body["log"]["source"] == payload["source"]
    assert body["log"]["log_level"] == "ERROR"
    assert body["log"]["message"] == payload["message"]
    # In the distributed architecture, alert is created asynchronously
    assert body["alert"] is None


def test_post_logs_invalid_payload_returns_422(client):
    invalid_payload = {
        "source": "firewall",
        "log_level": "INFO",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    response = client.post("/logs", json=invalid_payload)

    assert response.status_code == 422


def test_database_log_insertion(async_db_session, client):
    payload = {
        "source": "api-gateway",
        "log_level": "INFO",
        "message": "Request completed successfully",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_address": "10.10.10.1",
    }

    response = client.post("/logs", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["alert"] is None

    result = asyncio.run(async_db_session.execute(select(Log)))
    logs = result.scalars().all()

    assert len(logs) == 1
    assert logs[0].source == payload["source"]
    assert logs[0].log_level == payload["log_level"]

    alert_result = asyncio.run(async_db_session.execute(select(Alert)))
    alerts = alert_result.scalars().all()
    assert alerts == []


def test_enqueue_called_on_log_creation(client):
    """Verify the enqueue mock was called when a log is ingested."""
    import app.services.log_service as mod

    payload = {
        "source": "firewall",
        "log_level": "WARNING",
        "message": "Port scan detected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_address": "10.0.0.5",
    }

    response = client.post("/logs", json=payload)
    assert response.status_code == 201

    # The mock enqueue should have been awaited once
    assert mod._enqueue.await_count >= 1


def _insert_alert(async_session_maker, log_id, risk_score, created_at):
    async def _do():
        async with async_session_maker() as session:
            alert = Alert(
                id=uuid.uuid4(),
                log_id=log_id,
                severity="MEDIUM",
                reason="test",
                risk_score=risk_score,
                score_breakdown={"statistical": 0.1, "isolation": 0.1},
                anomaly_type="statistical_anomaly",
                created_at=created_at,
            )
            session.add(alert)
            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_do())
    finally:
        loop.close()


def test_get_ip_profile_not_found_returns_404(client):
    response = client.get("/ip/203.0.113.10/profile")
    assert response.status_code == 404


def test_get_ip_profile_returns_aggregates(client, async_session_maker):
    now = datetime.now(timezone.utc)

    payload_1 = {
        "source": "auth",
        "log_level": "ERROR",
        "message": "failed login",
        "timestamp": now.isoformat(),
        "ip_address": "10.10.10.10",
    }
    payload_2 = {
        "source": "auth",
        "log_level": "INFO",
        "message": "normal access",
        "timestamp": now.isoformat(),
        "ip_address": "10.10.10.10",
    }

    res1 = client.post("/logs", json=payload_1)
    res2 = client.post("/logs", json=payload_2)
    assert res1.status_code == 201
    assert res2.status_code == 201

    log_id_1 = uuid.UUID(res1.json()["log"]["id"])
    log_id_2 = uuid.UUID(res2.json()["log"]["id"])

    _insert_alert(async_session_maker, log_id_1, 0.8, now)
    _insert_alert(async_session_maker, log_id_2, 0.2, now)

    response = client.get("/ip/10.10.10.10/profile")
    assert response.status_code == 200

    body = response.json()
    assert body["ip"] == "10.10.10.10"
    assert body["total_logs"] == 2
    assert body["error_ratio"] == 0.5
    assert body["avg_risk_score"] == 0.5
    assert body["recent_alert_count"] == 2
    assert body["last_seen"] is not None
