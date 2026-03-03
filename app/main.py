"""SentinelAI – FastAPI application entrypoint."""

import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.dashboard_ws import router as dashboard_ws_router
from app.api.health import router as health_router
from app.api.ip_profile import router as ip_profile_router
from app.api.logs import router as logs_router
from app.database import Base, async_session, engine
from app.logging_config import setup_logging
from app.metrics import compute_metrics_response
from app.metrics import router as metrics_router
from app.middleware.request_id import RequestIdMiddleware
from app.realtime.connection_manager import connection_manager
from app.redis_pool import close_redis
from app.services.queue_service import listen_dashboard_events

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (idempotent), dispose engine on shutdown."""
    setup_logging()
    import app.models.log  # noqa: F401
    import app.models.alert  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def _metrics_broadcast_loop() -> None:
        while True:
            try:
                async with async_session() as session:
                    metrics_payload = (
                        await compute_metrics_response(session)
                    ).model_dump(mode="json")
                await connection_manager.broadcast(
                    {"type": "metrics", "payload": metrics_payload}
                )
            except Exception:
                logger.exception("Dashboard metrics broadcast loop error")
            await asyncio.sleep(5)

    async def _redis_event_bridge() -> None:
        await listen_dashboard_events(connection_manager.broadcast)

    tasks = [
        asyncio.create_task(_metrics_broadcast_loop()),
        asyncio.create_task(_redis_event_bridge()),
    ]

    yield

    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task

    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="SentinelAI",
    description="Phase 2 – Distributed event-driven security alerting",
    version="0.2.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

# Routers
app.include_router(logs_router)
app.include_router(alerts_router)
app.include_router(metrics_router)
app.include_router(ip_profile_router)
app.include_router(health_router)
app.include_router(dashboard_ws_router)


@app.get("/dlq", tags=["Observability"])
async def inspect_dlq():
    """Return the contents of the dead-letter queue."""
    from app.services.queue_service import dlq_list
    return await dlq_list()


@app.get("/queues", tags=["Observability"])
async def queue_stats():
    """Return current queue lengths."""
    from app.services.queue_service import queue_lengths
    return await queue_lengths()
