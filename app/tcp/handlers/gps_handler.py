"""
GPS 定位包处理器（高频简包，1 秒/次）。

完整流程（参考 ARCHITECTURE.md §3.1）：
  1. DeviceRegistry.push_point     — 更新内存最近轨迹点
  2. TrackSegmentService           — 获取/推进当前轨迹段
  3. LocationRepo.insert_batch     — 写入定位点到 DB
  4. GeofenceService.get_zones_at  — 查询当前围栏
  5. AlertService.process_location — 超速/越界/禁运检查
  6. CommandService.send           — 下发指令 + 记录日志
  7. EventRepo.insert              — 写入告警事件
  8. WorkStateService.update       — 更新作业状态机
  9. EventBus.publish              — 推送实时帧给 SSE 订阅者
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog
from redis.asyncio import Redis

from app.cache.pool import get_redis
from app.core.device_registry import DeviceRegistry, DeviceState
from app.core.event_bus import event_bus
from app.db.pool import get_pool
from app.db.repos.event_repo import EventRepo
from app.db.repos.location_repo import LocationRepo, LocationRow
from app.models.tcp_packets import GpsPacket
from app.services import alert_service, command_service, track_segment_service, work_state_service
from app.services.geofence_service import get_zones_at, wgs84_to_gcj02

logger = structlog.get_logger()

_location_repo = LocationRepo()
_event_repo = EventRepo()

# 业务配置由调用方（connection.py）传入，避免每包查 DB
_DEFAULT_SPEED_LIMIT = 80
_DEFAULT_PARK_MIN = 10
_DEFAULT_LOADING_MIN = 5
_DEFAULT_UNLOADING_MIN = 5
_DEFAULT_COOLDOWN_S = 10
_DEFAULT_TRANSPORT_TIMEOUT_MIN = 30


class GpsHandler:
    def __init__(
        self,
        registry: DeviceRegistry,
        global_speed_limit: int = _DEFAULT_SPEED_LIMIT,
        park_threshold_min: int = _DEFAULT_PARK_MIN,
        loading_dwell_min: int = _DEFAULT_LOADING_MIN,
        unloading_dwell_min: int = _DEFAULT_UNLOADING_MIN,
        alert_cooldown_s: int = _DEFAULT_COOLDOWN_S,
        transport_timeout_min: int = _DEFAULT_TRANSPORT_TIMEOUT_MIN,
        has_restricted_zones: bool = False,
    ) -> None:
        self._registry = registry
        self._speed_limit = global_speed_limit
        self._park_min = park_threshold_min
        self._loading_min = loading_dwell_min
        self._unloading_min = unloading_dwell_min
        self._cooldown_s = alert_cooldown_s
        self._transport_timeout_min = transport_timeout_min
        self._has_restricted = has_restricted_zones

    async def handle(
        self,
        state: DeviceState,
        packet: GpsPacket,
    ) -> None:
        recorded_at = datetime.now(tz=timezone.utc)
        redis: Redis = get_redis()
        pool = await get_pool()

        async with pool.acquire() as conn:
            await self._process(state, packet, conn, redis, recorded_at)

    async def _process(
        self,
        state: DeviceState,
        packet: GpsPacket,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        redis: Redis,
        recorded_at: datetime,
    ) -> None:
        fleet_id = state.fleet_id or 0

        # 速度推送优先（OLED 实时显示）：与后续 DB/告警操作完全解耦，
        # 确保即使 DB 抖动或告警处理异常也不影响设备侧速度更新。
        if packet.speed is not None:
            speed_msg = "{{v:{:.1f}}}".format(packet.speed).encode("ascii")
            await self._registry.send_command(state.device_id, speed_msg)

        # 1. 内存轨迹点
        await self._registry.push_point(state.device_id, packet)

        # 2. 获取/推进轨迹段
        # 装/卸料状态下抑制驻留分段，整个操作过程保持一条连续段
        from app.core.enums import WorkState as _WS
        _in_work_zone = state.current_work_state in (_WS.LOADING, _WS.UNLOADING)
        segment_id: Optional[int] = await track_segment_service.get_or_advance_segment(
            state=state,
            lat=packet.lat,
            lng=packet.lng,
            recorded_at=recorded_at,
            conn=conn,
            park_threshold_min=self._park_min,
            suppress_stationary_split=_in_work_zone,
        )

        # 3. 写入定位点
        await _location_repo.insert_batch(conn, [
            LocationRow(
                device_id=state.device_id,
                vehicle_id=state.vehicle_id,
                segment_id=segment_id,
                recorded_at=recorded_at,
                lat=packet.lat,
                lng=packet.lng,
                speed=packet.speed,
                altitude=packet.altitude,
                loc_type="gps",
            )
        ])

        # 4. 围栏判断
        zones = await get_zones_at(packet.lat, packet.lng, conn)

        # WGS-84 → GCJ-02：SSE 推送与高德地图展示均使用火星坐标
        lat_gcj, lng_gcj = wgs84_to_gcj02(packet.lat, packet.lng)

        # 5-7. 告警检查 → 指令下发 → 事件写入
        alert_result = await alert_service.process_location(
            state=state,
            packet=packet,
            zones_at_point=zones,
            has_restricted_zones=self._has_restricted,
            conn=conn,
            redis=redis,
            global_speed_limit=self._speed_limit,
            alert_cooldown_s=self._cooldown_s,
        )

        for alert in alert_result.alerts:
            # 组装附加信息：与手动下发事件保持 source 字段一致，便于前端统一展示
            detail: dict = {"source": "auto", "command": alert.command.value}
            if alert.ban_id is not None:
                detail["ban_id"] = alert.ban_id

            # 先写事件，拿到 event_id 再记 command_log
            event_id = await _event_repo.insert(
                conn,
                event_type=alert.event_type,
                occurred_at=recorded_at,
                device_id=state.device_id,
                vehicle_id=state.vehicle_id,
                zone_id=alert.zone_id,
                lat=packet.lat,
                lng=packet.lng,
                speed=alert.speed,
                cmd_sent=alert.command.value,
                detail=detail,
            )
            await command_service.send(
                device_id=state.device_id,
                cmd=alert.command,
                registry=self._registry,
                conn=conn,
                vehicle_id=state.vehicle_id,
                event_id=event_id,
                speed_kmh=alert.speed,
            )
            # 告警事件推送到 SSE（坐标同步转为 GCJ-02）
            alert_payload = {
                "event": "alert",
                "device_id": state.device_id,
                "vehicle_id": state.vehicle_id,
                "type": alert.event_type,
                "speed": alert.speed,
                "zone_id": alert.zone_id,
                "lat": lat_gcj,
                "lng": lng_gcj,
                "ts": recorded_at.isoformat(),
            }
            await event_bus.publish(f"alert:{fleet_id}", alert_payload)
            await event_bus.publish("alert:all", alert_payload)

        # 8. 作业状态机
        await work_state_service.update(
            state=state,
            zones_at_point=zones,
            speed=packet.speed,
            lat=packet.lat,
            lng=packet.lng,
            conn=conn,
            loading_dwell_min=self._loading_min,
            unloading_dwell_min=self._unloading_min,
            transport_timeout_min=self._transport_timeout_min,
        )

        # 10. 实时推送（SSE）
        location_payload = {
            "event": "location",
            "device_id": state.device_id,
            "vehicle_id": state.vehicle_id,
            "license_plate": state.license_plate,
            "lat": lat_gcj,
            "lng": lng_gcj,
            "speed": packet.speed,
            "altitude": packet.altitude,
            "ts": recorded_at.isoformat(),
        }
        await event_bus.publish(f"location:{fleet_id}", location_payload)
        await event_bus.publish("location:all", location_payload)
