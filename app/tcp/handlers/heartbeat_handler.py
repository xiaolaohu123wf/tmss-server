from __future__ import annotations

import structlog

from app.cache.heartbeat_cache import HeartbeatCache
from app.cache.pool import get_redis
from app.core.device_registry import DeviceRegistry

logger = structlog.get_logger()

_hb_cache = HeartbeatCache()


class HeartbeatHandler:
    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry

    async def handle(self, device_id: int) -> None:
        """更新内存心跳时间戳 + Redis 心跳 TTL。"""
        await self._registry.update_heartbeat(device_id)
        redis = get_redis()
        await _hb_cache.touch(redis, device_id)
        await logger.adebug("heartbeat_received", device_id=device_id)
