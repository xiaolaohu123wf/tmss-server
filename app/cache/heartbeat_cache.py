from __future__ import annotations

from typing import Optional

from redis.asyncio import Redis

_KEY_PREFIX = "hb:"


class HeartbeatCache:
    """Redis 心跳缓存，记录设备最后心跳时间戳（UNIX 时间戳字符串）。"""

    def __init__(self, ttl_s: int = 90) -> None:
        self._ttl = ttl_s

    async def touch(self, redis: Redis, device_id: int) -> None:
        """刷新设备心跳，重置 TTL。"""
        import time
        key = f"{_KEY_PREFIX}{device_id}"
        await redis.set(key, str(time.time()), ex=self._ttl)

    async def exists(self, redis: Redis, device_id: int) -> bool:
        """返回 True 表示设备心跳未过期（仍在线）。"""
        return bool(await redis.exists(f"{_KEY_PREFIX}{device_id}"))

    async def delete(self, redis: Redis, device_id: int) -> None:
        await redis.delete(f"{_KEY_PREFIX}{device_id}")
