from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from app.config import settings
from app.core.device_registry import device_registry
from app.core.task_registry import task_registry
from app.tcp.connection import ConnectionHandler

logger = structlog.get_logger()

_HB_CHECK_INTERVAL = 10   # 秒
_HB_TIMEOUT = 90          # 秒


async def _handle_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    handler = ConnectionHandler(reader, writer)
    await handler.run()


async def _heartbeat_monitor() -> None:
    """后台 Task：每 10 秒扫描离线设备，发布 EventBus 告警。"""
    from datetime import datetime, timezone
    from app.core.event_bus import event_bus

    while True:
        await asyncio.sleep(_HB_CHECK_INTERVAL)
        try:
            states = await device_registry.list_online()
            now = datetime.utcnow()
            for state in states:
                elapsed = (now - state.last_heartbeat_at).total_seconds()
                if elapsed > _HB_TIMEOUT:
                    topic = f"device_state"
                    await event_bus.publish(topic, {
                        "event": "heartbeat_timeout",
                        "device_id": state.device_id,
                        "imei": state.imei,
                        "elapsed_s": int(elapsed),
                    })
                    await logger.ainfo(
                        "heartbeat_timeout",
                        device_id=state.device_id,
                        imei=state.imei,
                        elapsed_s=int(elapsed),
                    )
        except Exception as exc:
            await logger.aerror("heartbeat_monitor_error", error=str(exc))


async def start_tcp_server() -> asyncio.Server:
    host = "0.0.0.0"
    port = settings.tcp_port

    server = await asyncio.start_server(_handle_client, host, port)
    await logger.ainfo("tcp_server_started", host=host, port=port)

    # 注册心跳监控后台任务
    task_registry.spawn(_heartbeat_monitor(), name="heartbeat_monitor")

    return server
