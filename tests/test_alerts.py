import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.alert import Alert
from app.models.log import Log


def _post_log(client, source, level, message, ip):
    return client.post(
        "/logs",
        json={
            "source": source,
            "log_level": level,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip_address": ip,
        },
    )


def _insert_alert(
    async_session_maker,
    log_id,
    severity,
    reason,
    risk_score=0.5,
    score_breakdown=None,
    anomaly_type="rule_match",
):
    """Directly insert an alert (simulating what the worker does)."""
    if score_breakdown is None:
        score_breakdown = {"statistical": 0.1, "isolation": 0.0}

    async def _do():
        async with async_session_maker() as session:
            alert = Alert(
                id=uuid.uuid4(),
                log_id=log_id,
                severity=severity,
                reason=reason,
                risk_score=risk_score,
                score_breakdown=score_breakdown,
                anomaly_type=anomaly_type,
                created_at=datetime.now(timezone.utc),
            )
            session.add(alert)
            await session.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_do())
    finally:
        loop.close()


def test_get_alerts_returns_created_alerts(client, async_session_maker):
    resp = _post_log(client, "auth", "ERROR", "failed login detected", "192.168.1.11")
    log_id = uuid.UUID(resp.json()["log"]["id"])

    _insert_alert(async_session_maker, log_id, "HIGH", "Log level is ERROR", risk_score=0.75)

    response = client.get("/alerts")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["severity"] == "HIGH"
    assert body["items"][0]["risk_score"] == 0.75
    assert "statistical" in body["items"][0]["score_breakdown"]
    assert body["items"][0]["anomaly_type"] is not None


def test_get_alerts_supports_severity_filtering(client, async_session_maker):
    resp1 = _post_log(client, "auth", "ERROR", "runtime error", "192.168.1.12")
    log_id_1 = uuid.UUID(resp1.json()["log"]["id"])
    _insert_alert(async_session_maker, log_id_1, "HIGH", "Log level is ERROR", risk_score=0.8)

    resp2 = _post_log(client, "waf", "INFO", "request burst", "172.16.0.9")
    log_id_2 = uuid.UUID(resp2.json()["log"]["id"])
    _insert_alert(async_session_maker, log_id_2, "MEDIUM", "IP rate exceeded", risk_score=0.45)

    all_alerts = client.get("/alerts")
    medium_only = client.get("/alerts", params={"severity": "MEDIUM"})
    high_only = client.get("/alerts", params={"severity": "HIGH"})

    assert all_alerts.status_code == 200
    assert medium_only.status_code == 200
    assert high_only.status_code == 200

    all_body = all_alerts.json()
    medium_body = medium_only.json()
    high_body = high_only.json()

    assert all_body["total"] == 2
    assert len(all_body["items"]) == 2
    assert medium_body["total"] == 1
    assert len(medium_body["items"]) == 1
    assert medium_body["items"][0]["severity"] == "MEDIUM"
    assert high_body["total"] == 1
    assert len(high_body["items"]) == 1
    assert high_body["items"][0]["severity"] == "HIGH"


def test_foreign_key_integrity_between_alert_and_log(async_db_session, async_session_maker, client):
    response = _post_log(client, "auth", "ERROR", "unauthorized access", "10.0.0.2")
    assert response.status_code == 201
    log_id = uuid.UUID(response.json()["log"]["id"])

    _insert_alert(async_session_maker, log_id, "HIGH", "unauthorized keyword")

    logs_result = asyncio.run(async_db_session.execute(select(Log)))
    alerts_result = asyncio.run(async_db_session.execute(select(Alert)))

    logs = logs_result.scalars().all()
    alerts = alerts_result.scalars().all()

    assert len(logs) == 1
    assert len(alerts) == 1
    assert alerts[0].log_id == logs[0].id


def test_idempotent_alert_unique_constraint(async_session_maker, client):
    """Inserting two alerts for the same log_id should fail (unique constraint)."""
    resp = _post_log(client, "auth", "ERROR", "double alert test", "10.0.0.3")
    log_id = uuid.UUID(resp.json()["log"]["id"])

    _insert_alert(async_session_maker, log_id, "HIGH", "first alert")

    import pytest
    with pytest.raises(Exception):
        _insert_alert(async_session_maker, log_id, "HIGH", "duplicate alert")


def test_alert_has_risk_score_and_breakdown(async_session_maker, client):
    """Verify new Phase 3 fields are persisted and returned."""
    resp = _post_log(client, "auth", "ERROR", "test risk fields", "10.0.0.4")
    log_id = uuid.UUID(resp.json()["log"]["id"])

    breakdown = {"statistical": 0.15, "isolation": 0.2}
    _insert_alert(
        async_session_maker, log_id, "HIGH", "anomaly",
        risk_score=0.72, score_breakdown=breakdown, anomaly_type="rule_match+isolation_anomaly",
    )

    response = client.get("/alerts")
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    alert = body["items"][0]
    assert alert["risk_score"] == 0.72
    assert alert["score_breakdown"]["statistical"] == 0.15
    assert alert["score_breakdown"]["isolation"] == 0.2
    assert "isolation_anomaly" in alert["anomaly_type"]


def test_get_alerts_supports_limit_offset_and_sort(client, async_session_maker):
    resp1 = _post_log(client, "auth", "ERROR", "older high", "10.0.0.10")
    log_id_1 = uuid.UUID(resp1.json()["log"]["id"])
    _insert_alert(async_session_maker, log_id_1, "HIGH", "older", risk_score=0.2)

    resp2 = _post_log(client, "auth", "WARN", "newer low", "10.0.0.11")
    log_id_2 = uuid.UUID(resp2.json()["log"]["id"])
    _insert_alert(async_session_maker, log_id_2, "LOW", "newer", risk_score=0.9)

    first_page = client.get("/alerts", params={"limit": 1, "offset": 0, "sort": "risk_score_desc"})
    second_page = client.get("/alerts", params={"limit": 1, "offset": 1, "sort": "risk_score_desc"})

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    first_body = first_page.json()
    second_body = second_page.json()

    assert first_body["total"] == 2
    assert first_body["limit"] == 1
    assert first_body["offset"] == 0
    assert first_body["items"][0]["risk_score"] == 0.9

    assert second_body["total"] == 2
    assert second_body["limit"] == 1
    assert second_body["offset"] == 1
    assert second_body["items"][0]["risk_score"] == 0.2


def test_get_alerts_rejects_invalid_sort(client):
    response = client.get("/alerts", params={"sort": "created_at desc"})
    assert response.status_code == 422
