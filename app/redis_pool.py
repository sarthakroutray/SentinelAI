"""Redis connection pool singleton.

Provides a shared ``redis.asyncio`` client backed by an internal connection
pool so that every queue / metrics / pub-sub operation reuses connections
instead of opening a new TCP socket per call.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings

_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client (lazy-initialised with a pool)."""
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
    return _pool


async def close_redis() -> None:
    """Shut down the Redis connection pool (call on app shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
