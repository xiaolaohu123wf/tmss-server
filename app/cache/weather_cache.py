from __future__ import annotations

from typing import Optional

from redis.asyncio import Redis

_KEY = "weather:current"


class WeatherCache:
    """Redis 天气缓存，存 '{temp}:{code}' 字符串，TTL 由业务配置决定。"""

    async def get(self, redis: Redis) -> Optional[str]:
        val = await redis.get(_KEY)
        return val if val else None

    async def set(self, redis: Redis, data: str, ttl_s: int) -> None:
        await redis.set(_KEY, data, ex=ttl_s)
