"""Lightweight API-key authentication for SentinelAI.

Usage (HTTP routes):
    from app.middleware.auth import verify_api_key

    @router.get("/protected", dependencies=[Depends(verify_api_key)])

Usage (WebSocket):
    from app.middleware.auth import verify_api_key_ws

    @router.websocket("/ws")
    async def ws(websocket: WebSocket):
        verify_api_key_ws(websocket)     # raises WebSocketException on failure
        await websocket.accept()

When ``API_KEY`` is empty (the default), authentication is disabled so
the system works out of the box in development environments.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Depends, Header, HTTPException, WebSocket, status
from starlette.websockets import WebSocketDisconnect

from app.config import settings

logger = logging.getLogger(__name__)


async def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency – validates the ``X-API-Key`` header.

    Skips validation entirely when ``settings.API_KEY`` is empty (dev mode).
    """
    if not settings.API_KEY:
        return  # Auth disabled

    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    if not hmac.compare_digest(x_api_key, settings.API_KEY):
        logger.warning("Invalid API key attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def verify_api_key_ws(websocket: WebSocket) -> None:
    """Synchronous check for WebSocket connections.

    Accepts the key from either the ``X-API-Key`` header or the
    ``api_key`` query parameter (useful for browser clients that
    cannot set custom headers on WebSocket connections).

    Raises ``WebSocketException`` on failure so the connection is
    rejected before ``accept()``.
    """
    if not settings.API_KEY:
        return  # Auth disabled

    key = (
        websocket.headers.get("x-api-key")
        or websocket.query_params.get("api_key")
    )

    if not key or not hmac.compare_digest(key, settings.API_KEY):
        raise WebSocketDisconnect(code=4401, reason="Invalid or missing API key")
