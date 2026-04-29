"""
指令下发服务：向已注册设备发送 ASCII 指令，并写入 command_log。
"""
from __future__ import annotations

from typing import Optional

import asyncpg
import structlog

from app.core.device_registry import DeviceRegistry
from app.core.enums import Command
from app.db.repos.command_log_repo import CommandLogRepo

logger = structlog.get_logger()

_cmd_log_repo = CommandLogRepo()


async def send(
    device_id: int,
    cmd: Command,
    registry: DeviceRegistry,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    vehicle_id: Optional[int] = None,
    event_id: Optional[int] = None,
    source: str = "auto",
    operator_id: Optional[int] = None,
) -> bool:
    """
    下发指令并记录日志。
    返回 True 表示指令已送达（TCP 写入成功）；False 表示设备不在线。
    """
    raw = (cmd.value + "\n").encode()
    delivered = await registry.send_command(device_id, raw)

    log_id = await _cmd_log_repo.insert(
        conn,
        cmd=cmd.value,
        device_id=device_id,
        vehicle_id=vehicle_id,
        source=source,
        operator_id=operator_id,
        event_id=event_id,
    )

    if delivered:
        await _cmd_log_repo.mark_delivered(conn, log_id)
        await logger.ainfo("command_sent", device_id=device_id, cmd=cmd.value)
    else:
        await logger.awarning("command_not_delivered", device_id=device_id, cmd=cmd.value)

    return delivered
