from __future__ import annotations

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None
_redis: Redis | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return _pool


async def init_redis() -> Redis:
    """在事件循环内创建 Redis 实例（lifespan 调用），避免在 worker thread 中创建 asyncio.Lock。"""
    global _redis
    if _redis is None:
        _redis = Redis(connection_pool=get_redis_pool())
    return _redis


def get_redis() -> Redis:
    """FastAPI Depends 使用。lifespan 必须先调用 init_redis()。"""
    if _redis is None:
        raise RuntimeError("Redis 未初始化，请确保 lifespan 已启动")
    return _redis


async def close_redis_pool() -> None:
    global _pool, _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
    if _pool is not None:
        await _pool.disconnect()
        _pool = None
