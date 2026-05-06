"""
作业状态会话服务（v1.2.0 精简版）。

v1.2.0 重构后，段类型管理已整合到 track_segment_service.process_gps_point()。
本模块仅保留 work_session 表的 CRUD 操作，供外部直接调用（如批量重分析、
管理接口等场景）。

实时路径不再直接调用本模块：gps_handler → track_segment_service.process_gps_point
（内部调用 _record_work_state_change 完成 work_session 写入）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog

from app.core.device_registry import DeviceState
from app.core.enums import WorkState
from app.db.repos.work_session_repo import WorkSessionRepo

logger = structlog.get_logger()

_work_session_repo = WorkSessionRepo()


async def open_session(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    vehicle_id: int,
    state: WorkState,
    zone_id: Optional[int] = None,
) -> None:
    """关闭当前开放会话并开启新会话。"""
    open_session = await _work_session_repo.find_open_by_vehicle(conn, vehicle_id)
    if open_session:
        await _work_session_repo.close_session(conn, open_session.id)
    await _work_session_repo.open_session(conn, vehicle_id, state, zone_id)


async def close_open_session(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    vehicle_id: int,
) -> None:
    """关闭当前开放会话（设备断线时调用）。"""
    open_session = await _work_session_repo.find_open_by_vehicle(conn, vehicle_id)
    if open_session:
        await _work_session_repo.close_session(conn, open_session.id)
