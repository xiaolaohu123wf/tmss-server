"""Redis SETNX 防抖：同一设备同一告警类型在 cooldown 秒内只触发一次。"""
from __future__ import annotations

from redis.asyncio import Redis


async def try_fire_alert(
    redis: Redis,
    device_id: int,
    alert_type: str,
    cooldown_s: int,
) -> bool:
    """
    返回 True 表示本次可以触发告警（首次或冷却已过）。
    返回 False 表示仍在防抖窗口内，应忽略。
    """
    key = f"debounce:{device_id}:{alert_type}"
    result = await redis.set(key, "1", nx=True, ex=cooldown_s)
    return result is not None
