"""
作业状态机服务。

基于车辆当前所在区域类型与驻留时长，更新 DeviceState.current_work_state
并写入 work_session 记录。

状态转移：
  ① 进入装料区 → 等待驻留 ≥ loading_dwell_min → LOADING
  ② 离开装料区（曾处于 LOADING）→ TRANSPORT_LOADED
  ③ 进入卸料区 → 等待驻留 ≥ unloading_dwell_min → UNLOADING
  ④ 离开卸料区（曾处于 UNLOADING）→ TRANSPORT_EMPTY
  ⑤ 其他情况 → UNKNOWN
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog

from app.core.device_registry import DeviceState
from app.core.enums import WorkState, ZoneType
from app.db.repos.geo_zone_repo import GeoZoneRow
from app.db.repos.work_session_repo import WorkSessionRepo

logger = structlog.get_logger()

_SPEED_STOP_THRESHOLD = 5.0   # km/h，低于此值视为停车

_work_session_repo = WorkSessionRepo()


async def update(
    state: DeviceState,
    zones_at_point: list[GeoZoneRow],
    speed: Optional[float],
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    loading_dwell_min: int,
    unloading_dwell_min: int,
) -> None:
    """
    根据当前点围栏与车速，更新 state.current_work_state，并操作 work_session 表。
    state 字段直接写入（DeviceState 是可变 dataclass）。
    """
    if state.vehicle_id is None:
        return

    now = datetime.now(tz=timezone.utc)
    is_stopped = speed is None or speed < _SPEED_STOP_THRESHOLD

    loading_zone = next((z for z in zones_at_point if z.zone_type == ZoneType.LOADING), None)
    unloading_zone = next((z for z in zones_at_point if z.zone_type == ZoneType.UNLOADING), None)

    dwell_zone = loading_zone or unloading_zone
    dwell_min = loading_dwell_min if loading_zone else unloading_dwell_min

    if dwell_zone and is_stopped:
        # 在装/卸料区停车
        if state.zone_entry_id != dwell_zone.id:
            # 切换到新区域，重置计时
            state.zone_entry_id = dwell_zone.id
            state.zone_entry_at = now

        # 检查驻留时长
        if state.zone_entry_at is not None:
            dwell_s = (now - state.zone_entry_at).total_seconds()
            target_state = (
                WorkState.LOADING if loading_zone else WorkState.UNLOADING
            )
            if dwell_s >= dwell_min * 60 and state.current_work_state != target_state:
                await _transition(state, target_state, dwell_zone.id, conn, now)
    else:
        # 离开驻留区或开始行驶
        if state.zone_entry_id is not None:
            # 刚刚离开装/卸料区，根据前序状态决定运输状态
            if state.current_work_state == WorkState.LOADING:
                await _transition(state, WorkState.TRANSPORT_LOADED, None, conn, now)
            elif state.current_work_state == WorkState.UNLOADING:
                await _transition(state, WorkState.TRANSPORT_EMPTY, None, conn, now)
            state.zone_entry_id = None
            state.zone_entry_at = None
        elif state.current_work_state == WorkState.UNKNOWN and dwell_zone is None:
            pass  # 保持 UNKNOWN，不产生新 session


async def _transition(
    state: DeviceState,
    new_state: WorkState,
    zone_id: Optional[int],
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    now: datetime,
) -> None:
    if state.vehicle_id is None:
        return
    old = state.current_work_state

    # 关闭进行中的 session
    open_session = await _work_session_repo.find_open_by_vehicle(conn, state.vehicle_id)
    if open_session:
        await _work_session_repo.close_session(conn, open_session.id)

    # 开启新 session（TRANSPORT_* 也建 session，方便统计运输时长）
    await _work_session_repo.open_session(conn, state.vehicle_id, new_state, zone_id)

    state.current_work_state = new_state
    await logger.ainfo(
        "work_state_transition",
        device_id=state.device_id,
        vehicle_id=state.vehicle_id,
        old=old,
        new=new_state,
    )
