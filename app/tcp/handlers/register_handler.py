from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import structlog

from app.core.device_registry import DeviceRegistry
from app.core.enums import Command
from app.core.event_bus import event_bus
from app.db.repos.device_repo import DeviceRepo

logger = structlog.get_logger()

_device_repo = DeviceRepo()


def _greeting_command() -> Command:
    """根据服务器当前时间返回欢迎语指令。"""
    hour = datetime.now().hour
    if 6 <= hour < 12:
        return Command.GM
    if 12 <= hour < 18:
        return Command.GA
    return Command.GN


class RegisterHandler:
    def __init__(self, registry: DeviceRegistry) -> None:
        self._registry = registry

    async def handle(
        self,
        imei: str,
        writer: asyncio.StreamWriter,
        conn,   # asyncpg.Connection
    ) -> Optional[int]:
        """
        处理设备注册：
        - 若 IMEI 在 device 表中存在，获取 device_id 及绑定的 vehicle_id/fleet_id
        - 若不存在，自动创建设备记录
        - 在 DeviceRegistry 中注册运行时状态
        - 仅首次注册（非重连）时下发欢迎语

        返回 device_id，失败返回 None。
        """
        # 查询或创建设备记录
        row = await _device_repo.find_by_imei(conn, imei)
        if row is None:
            device_id = await _device_repo.create(conn, imei=imei)
            vehicle_id = None
            fleet_id = None
            is_first_registration = True
            await logger.ainfo("device_auto_created", imei=imei, device_id=device_id)
        else:
            device_id = row.id
            # 查询当前绑定
            bind = await _device_repo.get_active_bind_by_device(conn, device_id)
            vehicle_id = bind.vehicle_id if bind else None
            fleet_id = await _get_fleet_id(conn, vehicle_id)
            is_first_registration = False

        # 检查是否已在线（重连），若是则不重复下发欢迎语
        existing = await self._registry.get(device_id)
        should_greet = existing is None  # 全新上线才欢迎

        await self._registry.register(
            device_id=device_id,
            imei=imei,
            writer=writer,
            vehicle_id=vehicle_id,
            fleet_id=fleet_id,
        )

        if should_greet:
            cmd = _greeting_command()
            writer.write(cmd.value.encode("ascii"))
            await writer.drain()
            await logger.ainfo(
                "greeting_sent", device_id=device_id, imei=imei, cmd=cmd.value
            )

        # 推送设备上线事件
        await event_bus.publish("device_state", {
            "event": "device_state",
            "type": "connected",
            "device_id": device_id,
            "imei": imei,
            "vehicle_id": vehicle_id,
            "fleet_id": fleet_id,
        })

        return device_id


async def _get_fleet_id(conn, vehicle_id: Optional[int]) -> Optional[int]:
    if vehicle_id is None:
        return None
    row = await conn.fetchrow(
        "SELECT fleet_id FROM vehicle WHERE id = $1 AND deleted_at IS NULL",
        vehicle_id,
    )
    return row["fleet_id"] if row else None
