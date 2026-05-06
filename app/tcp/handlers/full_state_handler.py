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
        # 全量包证明设备在线，刷新心跳时间戳（防止心跳监控误报 timeout）
        await self._registry.update_heartbeat(state.device_id)

        # 全量包中的 ICCID：仅当库内为空或为占位（na 等）时补全（设备字段 ic → packet.iccid）
        iccid_val = (packet.iccid or "").strip()
        if iccid_val:
            patched = await _device_repo.patch_iccid_if_empty(conn, state.device_id, iccid_val)
            if patched:
                await logger.adebug("device_iccid_patched", device_id=state.device_id)

        # 固件版本（有则更新；ICCID 改由 patch_iccid_if_empty 按需补全，避免覆盖已有卡号）
        if packet.firmware_version:
            await _device_repo.update_firmware(
                conn,
                device_id=state.device_id,
                firmware_version=packet.firmware_version,
                iccid=None,
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
