from __future__ import annotations

from typing import Optional

from redis.asyncio import Redis

_LEGACY_KEY = "weather:current"
_KEY_PREFIX = "weather:current:"


class WeatherCache:
    """Redis 天气缓存，存 '{temp}:{code}' 字符串，按城市分 key。"""

    @staticmethod
    def _normalize_city(city: str) -> str:
        return city.strip().lower() or "nanjing"

    def _city_key(self, city: str) -> str:
        return f"{_KEY_PREFIX}{self._normalize_city(city)}"

    async def get(self, redis: Redis, city: str) -> Optional[str]:
        val = await redis.get(self._city_key(city))
        return val if val else None

    async def get_legacy(self, redis: Redis) -> Optional[str]:
        val = await redis.get(_LEGACY_KEY)
        return val if val else None

    async def set(self, redis: Redis, city: str, data: str, ttl_s: int) -> None:
        await redis.set(self._city_key(city), data, ex=ttl_s)
        # 兼容旧代码：短期保留旧 key，避免升级期间读取到空值。
        await redis.set(_LEGACY_KEY, data, ex=ttl_s)
