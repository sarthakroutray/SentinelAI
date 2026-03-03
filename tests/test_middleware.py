"""Tests for the Request ID middleware."""

from datetime import datetime, timezone


def test_request_id_header_is_returned(client):
    """Every response should include an X-Request-ID header."""
    payload = {
        "source": "test",
        "log_level": "INFO",
        "message": "middleware test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/logs", json=payload)
    assert response.status_code == 201
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_request_id_echoed_when_provided(client):
    """If the client sends X-Request-ID, the server should echo it."""
    custom_id = "my-custom-request-123"
    response = client.get("/alerts", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id
