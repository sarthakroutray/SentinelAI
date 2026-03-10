"""Tests for API key authentication middleware."""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.middleware.auth import verify_api_key


# ── Helper to build test apps ───────────────────────────────────────


def _make_client(async_session_maker, api_key: str = ""):
    """Build a TestClient with API_KEY set to *api_key*."""
    from app.config import settings

    original_key = settings.API_KEY
    settings.API_KEY = api_key

    import app.services.log_service as log_service_mod
    from app.api.logs import router as logs_router
    from app.api.alerts import router as alerts_router

    app = FastAPI()
    app.include_router(logs_router)
    app.include_router(alerts_router)

    async def _override_get_session():
        async with async_session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    log_service_mod._enqueue = AsyncMock()

    client = TestClient(app)
    return client, settings, original_key


class TestAuthDisabled:
    """When API_KEY is empty, all routes should be accessible without a key."""

    def test_logs_accessible_without_key(self, async_session_maker):
        client, settings, original = _make_client(async_session_maker, api_key="")
        try:
            payload = {
                "source": "test",
                "log_level": "INFO",
                "message": "auth disabled test",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            resp = client.post("/logs", json=payload)
            assert resp.status_code == 201
        finally:
            settings.API_KEY = original

    def test_alerts_accessible_without_key(self, async_session_maker):
        client, settings, original = _make_client(async_session_maker, api_key="")
        try:
            resp = client.get("/alerts")
            assert resp.status_code == 200
        finally:
            settings.API_KEY = original


class TestAuthEnabled:
    """When API_KEY is set, routes require a valid X-API-Key header."""

    def test_missing_key_returns_401(self, async_session_maker):
        client, settings, original = _make_client(async_session_maker, api_key="test-secret-key")
        try:
            resp = client.get("/alerts")
            assert resp.status_code == 401
            assert "Missing" in resp.json()["detail"]
        finally:
            settings.API_KEY = original

    def test_wrong_key_returns_401(self, async_session_maker):
        client, settings, original = _make_client(async_session_maker, api_key="test-secret-key")
        try:
            resp = client.get("/alerts", headers={"X-API-Key": "wrong-key"})
            assert resp.status_code == 401
            assert "Invalid" in resp.json()["detail"]
        finally:
            settings.API_KEY = original

    def test_correct_key_returns_200(self, async_session_maker):
        client, settings, original = _make_client(async_session_maker, api_key="test-secret-key")
        try:
            resp = client.get("/alerts", headers={"X-API-Key": "test-secret-key"})
            assert resp.status_code == 200
        finally:
            settings.API_KEY = original

    def test_post_with_correct_key(self, async_session_maker):
        client, settings, original = _make_client(async_session_maker, api_key="test-secret-key")
        try:
            payload = {
                "source": "test",
                "log_level": "INFO",
                "message": "authenticated request",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            resp = client.post(
                "/logs",
                json=payload,
                headers={"X-API-Key": "test-secret-key"},
            )
            assert resp.status_code == 201
        finally:
            settings.API_KEY = original
