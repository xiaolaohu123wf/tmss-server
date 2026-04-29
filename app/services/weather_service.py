from __future__ import annotations

from typing import Optional

import httpx
import structlog

from app.cache.pool import get_redis
from app.cache.weather_cache import WeatherCache
from app.config import settings

logger = structlog.get_logger()

_CACHE = WeatherCache()

_WEATHER_CODE_MAP = [
    ({"thunder", "storm", "blizzard"}, 7),
    ({"snow", "sleet", "ice"}, 5),
    ({"fog", "mist", "haze"}, 6),
    ({"heavy rain", "torrential", "pouring"}, 4),
    ({"rain", "drizzle", "shower"}, 3),
    ({"overcast"}, 2),
    ({"partly", "cloudy", "cloud"}, 1),
]


def _map_weather_code(desc: str) -> int:
    low = desc.lower()
    for keywords, code in _WEATHER_CODE_MAP:
        if any(w in low for w in keywords):
            return code
    return 0  # sunny / clear


async def _fetch_weather(city: str) -> Optional[str]:
    url = f"{settings.weather_api_url}/{city}?format=j1"
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            cur = data["current_condition"][0]
            temp = int(cur["temp_C"])
            desc = cur["weatherDesc"][0]["value"]
            code = _map_weather_code(desc)
            return f"{temp}:{code}"
    except Exception as exc:
        await logger.awarning("weather_fetch_failed", error=str(exc), city=city)
        return None


class WeatherService:
    async def get_weather_reply(self, city: str, cache_ttl_s: int = 1800) -> str:
        """返回 w{temp}:{code} 格式字符串，优先读缓存。"""
        redis = get_redis()
        cached = await _CACHE.get(redis)
        if cached:
            return f"w{cached}"

        data = await _fetch_weather(city)
        if data:
            await _CACHE.set(redis, data, ttl_s=cache_ttl_s)
            return f"w{data}"
        return "w0:0"   # 降级：返回晴天/0°C
