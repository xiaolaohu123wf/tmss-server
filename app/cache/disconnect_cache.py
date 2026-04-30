from __future__ import annotations

import time

from redis.asyncio import Redis

_KEY_PREFIX = "disconnect_at:"
# TTL = 3600s：key 存在 → 设备断线不足 1 小时；key 过期/不存在 → 离线超 1h 或首次上线
_TTL_S = 3600


class DisconnectCache:
    """记录设备最后断线的 UNIX 时间戳，TTL 1 小时。
    用于注册时判断是否需要重新下发欢迎语：
      - key 存在（离线 < 1h）→ 不发欢迎
      - key 不存在（离线 > 1h 或首次连线）→ 发欢迎
    """

    async def record(self, redis: Redis, device_id: int) -> None:
        """断线时调用，写入当前时间戳并设置 1 小时 TTL。"""
        await redis.set(
            f"{_KEY_PREFIX}{device_id}",
            str(time.time()),
            ex=_TTL_S,
        )

    async def was_recently_disconnected(self, redis: Redis, device_id: int) -> bool:
        """True = 设备断线不足 1 小时（key 未过期）；False = 首次或离线超 1h。"""
        return bool(await redis.exists(f"{_KEY_PREFIX}{device_id}"))


disconnect_cache = DisconnectCache()
