from __future__ import annotations

import asyncio
from datetime import datetime

import structlog

from app.services.weather_service import WeatherService
from app.tcp.raw_trace import record_tx

logger = structlog.get_logger()

_weather_svc = WeatherService()

# 天气城市从 business_config 动态读取（此处先用默认值）
_DEFAULT_CITY = "Nanjing"
_WEATHER_CACHE_TTL_S = 1800  # 30 分钟


class TimeWeatherHandler:
    async def handle_time(self, writer: asyncio.StreamWriter) -> None:
        """响应 rt 请求，回复 t{HHMMSS}。"""
        now = datetime.now()
        reply = f"t{now.hour:02d}{now.minute:02d}{now.second:02d}"
        out = reply.encode("ascii")
        record_tx(writer, out)
        writer.write(out)
        await writer.drain()
        await logger.adebug("time_reply_sent", reply=reply)

    async def handle_weather(
        self, writer: asyncio.StreamWriter, city: str = _DEFAULT_CITY
    ) -> None:
        """响应 rw 请求，回复 w{temp}:{code}。"""
        reply = await _weather_svc.get_weather_reply(city, _WEATHER_CACHE_TTL_S)
        out = reply.encode("ascii")
        record_tx(writer, out)
        writer.write(out)
        await writer.drain()
        await logger.adebug("weather_reply_sent", reply=reply, city=city)
