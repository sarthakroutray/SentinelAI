"""WebSocket endpoint for realtime dashboard streaming."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.middleware.auth import verify_api_key_ws
from app.realtime.connection_manager import connection_manager

router = APIRouter(tags=["Realtime"])


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket) -> None:
    verify_api_key_ws(websocket)
    await connection_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await connection_manager.disconnect(websocket)

