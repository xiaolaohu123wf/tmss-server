from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import structlog

from app.core.enums import WorkState
from app.models.tcp_packets import GpsPacket
from app.tcp.raw_trace import record_tx

logger = structlog.get_logger()

RECENT_POINTS_BUF = 300


@dataclass
class DeviceState:
    device_id: int
    imei: str
    vehicle_id: Optional[int]
    fleet_id: Optional[int]
    writer: asyncio.StreamWriter
    last_heartbeat_at: datetime
    connected_at: datetime
    license_plate: Optional[str] = None
    recent_points: deque = field(default_factory=lambda: deque(maxlen=RECENT_POINTS_BUF))
    current_work_state: WorkState = WorkState.UNKNOWN
    active_zone_ids: set = field(default_factory=set)
    # 轨迹分段追踪
    current_segment_id: Optional[int] = None
    last_point_at: Optional[datetime] = None
    # 停车驻留检测（位移半径 < PARK_STATIONARY_RADIUS_M 即视为停车）
    stationary_anchor_lat: Optional[float] = None
    stationary_anchor_lng: Optional[float] = None
    stationary_since: Optional[datetime] = None   # 最后一次移动超出半径的时刻
    # 作业状态机：当前驻留区的进入时刻 (用于 dwell 计算)
    zone_entry_at: Optional[datetime] = None
    zone_entry_id: Optional[int] = None   # 正在计时驻留的 zone_id
    # 防止短暂重连期间两个连接并发开段（asyncio 协作式，Lock 足够）
    segment_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class DeviceRegistry:
    """在线设备运行时状态注册表（单例，进程内共享）。"""

    def __init__(self) -> None:
        self._devices: dict[int, DeviceState] = {}
        self._by_imei: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        device_id: int,
        imei: str,
        writer: asyncio.StreamWriter,
        vehicle_id: Optional[int] = None,
        fleet_id: Optional[int] = None,
        license_plate: Optional[str] = None,
    ) -> DeviceState:
        async with self._lock:
            now = datetime.utcnow()
            existing = self._devices.get(device_id)
            if existing is not None:
                # 设备重连（旧连接尚未清理或短暂断线）：只更新连接相关字段，
                # 保留轨迹段状态（current_segment_id / last_point_at / 驻留锚点）
                # 以及车辆绑定（vehicle_id 由 update_binding 管理，不被注册覆盖）。
                existing.writer = writer
                existing.last_heartbeat_at = now
                self._by_imei[imei] = device_id
                await logger.ainfo("device_reconnected", device_id=device_id, imei=imei)
                return existing
            state = DeviceState(
                device_id=device_id,
                imei=imei,
                vehicle_id=vehicle_id,
                fleet_id=fleet_id,
                license_plate=license_plate,
                writer=writer,
                last_heartbeat_at=now,
                connected_at=now,
            )
            self._devices[device_id] = state
            self._by_imei[imei] = device_id
        await logger.ainfo("device_registered", device_id=device_id, imei=imei)
        return state

    async def unregister(self, device_id: int) -> None:
        async with self._lock:
            state = self._devices.pop(device_id, None)
            if state:
                self._by_imei.pop(state.imei, None)
        if state:
            await logger.ainfo("device_unregistered", device_id=device_id, imei=state.imei)

    async def get(self, device_id: int) -> Optional[DeviceState]:
        return self._devices.get(device_id)

    async def get_by_imei(self, imei: str) -> Optional[DeviceState]:
        device_id = self._by_imei.get(imei)
        if device_id is None:
            return None
        return self._devices.get(device_id)

    async def list_online(self, fleet_id: Optional[int] = None) -> list[DeviceState]:
        states = list(self._devices.values())
        if fleet_id is not None:
            states = [s for s in states if s.fleet_id == fleet_id]
        return states

    async def update_heartbeat(self, device_id: int) -> None:
        state = self._devices.get(device_id)
        if state:
            state.last_heartbeat_at = datetime.utcnow()

    async def push_point(self, device_id: int, point: GpsPacket) -> None:
        state = self._devices.get(device_id)
        if state:
            state.recent_points.append(point)

    async def update_binding(
        self,
        device_id: int,
        vehicle_id: Optional[int],
        fleet_id: Optional[int],
        license_plate: Optional[str] = None,
    ) -> bool:
        """绑定/解绑后刷新内存状态，若设备不在线则返回 False。"""
        state = self._devices.get(device_id)
        if state is None:
            return False
        state.vehicle_id = vehicle_id
        state.fleet_id = fleet_id
        state.license_plate = license_plate
        # 车辆绑定发生变化，重置轨迹段指针：
        # 下一个 GPS 包到达时，旧段会被正确关闭并以新 vehicle_id 开启新段。
        state.current_segment_id = None
        state.last_point_at = None
        state.stationary_anchor_lat = None
        state.stationary_anchor_lng = None
        state.stationary_since = None
        await logger.ainfo(
            "device_binding_updated",
            device_id=device_id,
            vehicle_id=vehicle_id,
            fleet_id=fleet_id,
        )
        return True

    async def send_command(self, device_id: int, cmd: bytes) -> bool:
        state = self._devices.get(device_id)
        if state is None:
            return False
        try:
            record_tx(state.writer, cmd)
            state.writer.write(cmd)
            await state.writer.drain()
            return True
        except Exception as exc:
            await logger.awarning(
                "send_command_failed",
                device_id=device_id,
                cmd=cmd[:40],
                error=str(exc),
            )
            return False


device_registry = DeviceRegistry()
