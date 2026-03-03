import asyncio
import os
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/sentinel_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.api.alerts import router as alerts_router
from app.api.health import router as health_router
from app.api.ip_profile import router as ip_profile_router
from app.api.logs import router as logs_router
from app.database import Base, get_session
from app.metrics import router as metrics_router
from app.middleware.request_id import RequestIdMiddleware
from app.services import rule_engine
from app.services.baseline_store import baseline_store
from app.services.isolation_engine import isolation_engine
from app.services.profile_store import profile_store
import app.services.log_service as log_service_mod
import app.metrics as metrics_mod


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="session")
def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run_async(_setup())

    yield engine

    async def _teardown():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    _run_async(_teardown())


@pytest.fixture(scope="session")
def async_session_maker(test_engine):
    return async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
def reset_state(async_session_maker):
    async def _reset_db():
        async with async_session_maker() as session:
            await session.execute(text("DELETE FROM alerts"))
            await session.execute(text("DELETE FROM logs"))
            await session.commit()

    _run_async(_reset_db())
    rule_engine._ip_tracker._buckets.clear()

    # Reset metrics counters
    with metrics_mod._lock:
        for key in metrics_mod._counters:
            metrics_mod._counters[key] = 0

    # Reset metrics response cache
    metrics_mod._metrics_cache = None
    metrics_mod._metrics_cache_at = 0.0

    # Reset Phase 3 singletons
    baseline_store.clear()
    isolation_engine.reset()
    profile_store.clear()

    # Reset the lazy enqueue reference so tests don't try to hit Redis
    log_service_mod._enqueue = None


@pytest.fixture
def async_db_session(async_session_maker) -> Generator[AsyncSession, None, None]:
    session = async_session_maker()
    try:
        yield session
    finally:
        _run_async(session.close())


@pytest.fixture
def client(async_session_maker) -> Generator[TestClient, None, None]:
    """TestClient with Redis enqueue mocked out."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.include_router(logs_router)
    app.include_router(alerts_router)
    app.include_router(metrics_router)
    app.include_router(ip_profile_router)
    app.include_router(health_router)

    async def _override_get_session():
        async with async_session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session

    # Disable Redis enqueue during tests
    log_service_mod._enqueue = AsyncMock()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    log_service_mod._enqueue = None
