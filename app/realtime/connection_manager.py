"""Async WebSocket connection manager for dashboard realtime updates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


@dataclass(slots=True)
class _ConnectionState:
    queue: asyncio.Queue[dict[str, Any]]
    sender_task: asyncio.Task[None]


class ConnectionManager:
    def __init__(self, queue_size: int = 128, send_timeout_s: float = 1.0) -> None:
        self._connections: dict[WebSocket, _ConnectionState] = {}
        self._lock = asyncio.Lock()
        self._queue_size = queue_size
        self._send_timeout_s = send_timeout_s

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        sender_task = asyncio.create_task(self._sender(websocket, queue))

        async with self._lock:
            self._connections[websocket] = _ConnectionState(
                queue=queue,
                sender_task=sender_task,
            )

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            state = self._connections.pop(websocket, None)

        if state is not None:
            state.sender_task.cancel()
            try:
                await state.sender_task
            except asyncio.CancelledError:
                pass

        try:
            await websocket.close()
        except Exception:
            pass

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            items = list(self._connections.items())

        stale: list[WebSocket] = []
        for websocket, state in items:
            try:
                state.queue.put_nowait(message)
            except asyncio.QueueFull:
                stale.append(websocket)

        for websocket in stale:
            await self.disconnect(websocket)

    async def _sender(
        self,
        websocket: WebSocket,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        try:
            while True:
                payload = await queue.get()
                await asyncio.wait_for(
                    websocket.send_json(payload),
                    timeout=self._send_timeout_s,
                )
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            # Client gone or unresponsive – clean up handled in finally.
            pass
        finally:
            async with self._lock:
                state = self._connections.get(websocket)
                if state is not None and state.queue is queue:
                    self._connections.pop(websocket, None)

            try:
                await websocket.close()
            except Exception:
                pass


connection_manager = ConnectionManager()
