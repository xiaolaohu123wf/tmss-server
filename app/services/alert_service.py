"""
告警服务：处理单个定位包，检查超速、越界、禁运时段。

每个有效 GPS 包到达时调用 process_location()，
返回需要下发的指令及需要写入的事件列表，调用者负责实际下发。
"""
from __future__ import annotations

import asyncio
import time as _t
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import asyncpg
import structlog
from redis.asyncio import Redis

from app.cache.debounce import try_fire_alert
from app.core.device_registry import DeviceState
from app.core.enums import Command, EventType, ZoneType
from app.db.repos.geo_zone_repo import GeoZoneRow
from app.db.repos.operation_ban_repo import OperationBanRepo, OperationBanRow
from app.models.tcp_packets import GpsPacket
from app.services.geofence_service import get_zone_speed_limit

logger = structlog.get_logger()

_op_ban_repo = OperationBanRepo()
_ban_cache: Optional[list[OperationBanRow]] = None
_ban_cache_lock: Optional[asyncio.Lock] = None
_ban_loaded_at: float = 0.0
_BAN_TTL = 300.0


def _get_ban_lock() -> asyncio.Lock:
    global _ban_cache_lock
    if _ban_cache_lock is None:
        _ban_cache_lock = asyncio.Lock()
    return _ban_cache_lock


async def _get_bans(conn: asyncpg.Connection) -> list[OperationBanRow]:  # type: ignore[type-arg]
    global _ban_cache, _ban_loaded_at
    async with _get_ban_lock():
        if _ban_cache is None or _t.monotonic() - _ban_loaded_at > _BAN_TTL:
            _ban_cache = await _op_ban_repo.find_all_enabled(conn)
            _ban_loaded_at = _t.monotonic()
    return _ban_cache  # type: ignore[return-value]


def _in_ban_period(ban: OperationBanRow, now_local: datetime) -> bool:
    """跨零点兼容的禁运时段判断。"""
    if now_local.isoweekday() not in ban.weekdays:
        return False
    cur = now_local.time()
    s, e = ban.start_time, ban.end_time
    if s <= e:
        return s <= cur <= e
    return cur >= s or cur <= e   # 跨零点，例如 22:00–06:00


# ---------------------------------------------------------------------------

@dataclass
class PendingAlert:
    command: Command
    event_type: EventType
    zone_id: Optional[int] = None
    ban_id: Optional[int] = None
    speed: Optional[float] = None


@dataclass
class AlertResult:
    alerts: list[PendingAlert] = field(default_factory=list)


# ---------------------------------------------------------------------------

async def process_location(
    state: DeviceState,
    packet: GpsPacket,
    zones_at_point: list[GeoZoneRow],   # 当前点命中的启用围栏
    has_restricted_zones: bool,          # 系统中是否存在任何限行围栏
    conn: asyncpg.Connection,           # type: ignore[type-arg]
    redis: Redis,
    global_speed_limit: int,
    alert_cooldown_s: int,
) -> AlertResult:
    """
    参数：
      zones_at_point      — 由 geofence_service.get_zones_at() 返回的当前点围栏列表
      has_restricted_zones — 系统中是否配置了限行围栏（用于越界判定）
    """
    result = AlertResult()
    now_local = datetime.now()

    # 1. 超速
    if packet.speed is not None:
        limit, speed_zone_id = get_zone_speed_limit(zones_at_point, global_speed_limit)
        if packet.speed > limit:
            if await try_fire_alert(redis, state.device_id, "overspeed", alert_cooldown_s):
                result.alerts.append(PendingAlert(
                    command=Command.WS,
                    event_type=EventType.OVERSPEED,
                    zone_id=speed_zone_id,
                    speed=packet.speed,
                ))
                await logger.ainfo(
                    "alert_overspeed",
                    device_id=state.device_id,
                    speed=packet.speed,
                    limit=limit,
                )

    # 2. 越界（限行围栏）：有限行围栏配置 且 当前点不在任何限行围栏内
    in_restricted = any(z.zone_type == ZoneType.RESTRICTED for z in zones_at_point)
    if has_restricted_zones and not in_restricted:
        if await try_fire_alert(redis, state.device_id, "geofence", alert_cooldown_s):
            result.alerts.append(PendingAlert(
                command=Command.WA,
                event_type=EventType.GEOFENCE_VIOLATION,
            ))
            await logger.ainfo("alert_geofence_violation", device_id=state.device_id)

    # 3. 禁运时段
    zone_ids = {z.id for z in zones_at_point}
    for ban in await _get_bans(conn):
        if not _in_ban_period(ban, now_local):
            continue
        if ban.zone_id is not None and ban.zone_id not in zone_ids:
            continue
        if await try_fire_alert(redis, state.device_id, f"ban_{ban.id}", alert_cooldown_s):
            result.alerts.append(PendingAlert(
                command=Command.WA,
                event_type=EventType.BAN_VIOLATION,
                ban_id=ban.id,
                zone_id=ban.zone_id,
            ))
            await logger.ainfo("alert_ban", device_id=state.device_id, ban_id=ban.id)
        break  # 同设备同时刻最多触发一条禁运告警

    return result
