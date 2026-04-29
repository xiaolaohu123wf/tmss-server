"""
全量状态包处理器（低频，10~150 秒/次）。

更新设备的 ICCID、固件版本；若包含有效 GPS 坐标则也写入定位点。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog

from app.core.device_registry import DeviceRegistry, DeviceState
from app.db.pool import get_pool
from app.db.repos.device_repo import DeviceRepo
from app.db.repos.location_repo import LocationRepo, LocationRow
from app.models.tcp_packets import FullStatePacket

logger = structlog.get_logger()

_device_repo = DeviceRepo()
_location_repo = LocationRepo()


class FullStateHandler:
    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry

    async def handle(self, state: DeviceState, packet: FullStatePacket) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await self._process(state, packet, conn)

    async def _process(
        self,
        state: DeviceState,
        packet: FullStatePacket,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
    ) -> None:
        # 更新固件/ICCID（firmware_version 必须非空才能调用，iccid 通过 COALESCE 更新）
        if packet.firmware_version:
            await _device_repo.update_firmware(
                conn,
                device_id=state.device_id,
                firmware_version=packet.firmware_version,
                iccid=packet.iccid,
            )

        # LBS 或 GPS 定位点（全量包优先使用 GPS，降级到 LBS）
        lat: Optional[float] = None
        lng: Optional[float] = None
        loc_type = "lbs"

        if packet.is_gps_fixed():
            lat = packet.gps_lat()
            lng = packet.gps_lng()
            loc_type = "gps"
        elif packet.lbs_lat() and packet.lbs_lng():
            lat = packet.lbs_lat()
            lng = packet.lbs_lng()

        if lat is not None and lng is not None:
            recorded_at = datetime.now(tz=timezone.utc)
            await _location_repo.insert_batch(conn, [
                LocationRow(
                    device_id=state.device_id,
                    vehicle_id=state.vehicle_id,
                    segment_id=state.current_segment_id,
                    recorded_at=recorded_at,
                    lat=lat,
                    lng=lng,
                    speed=packet.gps_speed() if loc_type == "gps" else None,
                    altitude=packet.gps_altitude() if loc_type == "gps" else None,
                    loc_type=loc_type,
                )
            ])
            await logger.adebug(
                "full_state_location_saved",
                device_id=state.device_id,
                loc_type=loc_type,
            )
