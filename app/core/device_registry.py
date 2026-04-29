from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import structlog

from app.core.enums import WorkState
from app.models.tcp_packets import GpsPacket

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
    recent_points: deque = field(default_factory=lambda: deque(maxlen=RECENT_POINTS_BUF))
    current_work_state: WorkState = WorkState.UNKNOWN
    active_zone_ids: set = field(default_factory=set)


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
    ) -> DeviceState:
        async with self._lock:
            now = datetime.utcnow()
            state = DeviceState(
                device_id=device_id,
                imei=imei,
                vehicle_id=vehicle_id,
                fleet_id=fleet_id,
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

    async def send_command(self, device_id: int, cmd: bytes) -> bool:
        state = self._devices.get(device_id)
        if state is None:
            return False
        try:
            state.writer.write(cmd)
            await state.writer.drain()
            return True
        except Exception:
            return False


device_registry = DeviceRegistry()
