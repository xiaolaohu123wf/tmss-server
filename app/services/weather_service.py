from __future__ import annotations

from typing import Optional

import httpx
import structlog

from app.cache.pool import get_redis
from app.cache.weather_cache import WeatherCache
from app.config import settings

logger = structlog.get_logger()

_CACHE = WeatherCache()

# 注意：wttr.in 春季对长三角地区极频繁返回 "Thundery outbreaks possible" /
# "Patchy rain with thunder"，这类描述含 "thunder" 但并非真正雷暴。
# 只有 "thunderstorm" 精确词才映射到 7；其余含 "thunder" 的降级为大雨（4）。
def _map_weather_code(desc: str) -> int:
    low = desc.lower()
    # 7：确认雷暴 / 暴风雪
    if "thunderstorm" in low or "blizzard" in low:
        return 7
    # 5：降雪 / 冻雨 / 冰雹
    if any(w in low for w in ("snow", "sleet", "ice pellet", "blowing snow")):
        return 5
    # 6：雾 / 霾
    if any(w in low for w in ("fog", "mist", "haze")):
        return 6
    # 4：雷阵雨可能（含 thunder 但非 thunderstorm）/ 大雨
    if "thunder" in low:
        return 4
    if any(w in low for w in ("heavy rain", "torrential", "pouring", "heavy shower")):
        return 4
    # 3：小雨 / 阵雨 / 毛毛雨
    if any(w in low for w in ("rain", "drizzle", "shower", "patchy rain")):
        return 3
    # 2：阴
    if "overcast" in low:
        return 2
    # 1：多云
    if any(w in low for w in ("partly", "cloudy", "cloud")):
        return 1
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
