"""
作业状态机服务。

基于车辆当前所在区域类型与驻留时长，更新 DeviceState.current_work_state
并写入 work_session 记录。同时协调轨迹段类型的切换：

  进入装/卸料区驻留确认 → switch_segment_type('loading'/'unloading')
  离开装/卸料区 → switch_segment_type(None)（普通行驶段）

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
from app.services import track_segment_service

logger = structlog.get_logger()

_SPEED_STOP_THRESHOLD = 5.0   # km/h，低于此值视为停车

_work_session_repo = WorkSessionRepo()


async def update(
    state: DeviceState,
    zones_at_point: list[GeoZoneRow],
    speed: Optional[float],
    lat: float,
    lng: float,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    loading_dwell_s: int,
    unloading_dwell_s: int,
    transport_timeout_min: int = 30,
) -> None:
    """
    根据当前点围栏与车速，更新 state.current_work_state，并操作 work_session 表。
    lat/lng 为 WGS-84 原始坐标，用于在作业状态切换时正确关闭/开启轨迹段。
    loading_dwell_s / unloading_dwell_s：装/卸料最短驻留时长，单位**秒**（与 DB 存储单位一致）。
    transport_timeout_min: 运输超时阈值（分钟），0 表示不启用超时检测。
    """
    if state.vehicle_id is None:
        return

    now = datetime.now(tz=timezone.utc)
    is_stopped = speed is None or speed < _SPEED_STOP_THRESHOLD

    loading_zone = next((z for z in zones_at_point if z.zone_type == ZoneType.LOADING), None)
    unloading_zone = next((z for z in zones_at_point if z.zone_type == ZoneType.UNLOADING), None)

    dwell_zone = loading_zone or unloading_zone

    # ── 运输超时检测 ──────────────────────────────────────────────────────────
    # 车辆离开装/卸料区后若超过 transport_timeout_min 分钟仍未抵达下一站 → UNKNOWN
    if (
        transport_timeout_min > 0
        and state.current_work_state in (WorkState.TRANSPORT_LOADED, WorkState.TRANSPORT_EMPTY)
        and state.transport_started_at is not None
        and dwell_zone is None  # 尚未进入下一装/卸料区
    ):
        elapsed_min = (now - state.transport_started_at).total_seconds() / 60.0
        if elapsed_min >= transport_timeout_min:
            await logger.ainfo(
                "transport_timeout",
                device_id=state.device_id,
                vehicle_id=state.vehicle_id,
                elapsed_min=round(elapsed_min, 1),
            )
            await _transition(state, WorkState.UNKNOWN, None, lat, lng, conn, now)
            state.transport_started_at = None
            return  # 本轮不再做围栏驻留检查

    # 当前围栏对应的驻留阈值（秒）
    dwell_threshold_s = loading_dwell_s if loading_zone else unloading_dwell_s

    if dwell_zone:
        # 车辆在装/卸料围栏内
        if state.zone_entry_id != dwell_zone.id:
            # 进入新区域（或从另一围栏切换），重置驻留计时
            state.zone_entry_id = dwell_zone.id
            state.zone_entry_at = now

        # 仅在停车状态下推进状态；在围栏内缓慢行驶时保留计时但不切换状态
        if is_stopped and state.zone_entry_at is not None:
            elapsed_s = (now - state.zone_entry_at).total_seconds()
            target_state = WorkState.LOADING if loading_zone else WorkState.UNLOADING
            # dwell_threshold_s 单位为秒，与 elapsed_s 直接比较（无需乘 60）
            if elapsed_s >= dwell_threshold_s and state.current_work_state != target_state:
                await _transition(state, target_state, dwell_zone.id, lat, lng, conn, now)
    else:
        # 车辆已离开装/卸料围栏
        if state.zone_entry_id is not None:
            # 根据离开前的作业状态切换为运输状态
            if state.current_work_state == WorkState.LOADING:
                await _transition(state, WorkState.TRANSPORT_LOADED, None, lat, lng, conn, now)
            elif state.current_work_state == WorkState.UNLOADING:
                await _transition(state, WorkState.TRANSPORT_EMPTY, None, lat, lng, conn, now)
            state.zone_entry_id = None
            state.zone_entry_at = None


async def _transition(
    state: DeviceState,
    new_state: WorkState,
    zone_id: Optional[int],
    lat: float,
    lng: float,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    now: datetime,
) -> None:
    if state.vehicle_id is None:
        return
    old = state.current_work_state

    # ── work_session 管理 ─────────────────────────────────────────────────────
    open_session = await _work_session_repo.find_open_by_vehicle(conn, state.vehicle_id)
    if open_session:
        await _work_session_repo.close_session(conn, open_session.id)
    await _work_session_repo.open_session(conn, state.vehicle_id, new_state, zone_id)

    state.current_work_state = new_state

    # ── 轨迹段类型切换 ────────────────────────────────────────────────────────
    # 进入装/卸料状态 → 开新的类型段，后续 GPS 包归入此段，不再按驻留切分
    # 进入运输/空返状态 → 关闭类型段，开普通段
    if new_state == WorkState.LOADING:
        await track_segment_service.switch_segment_type(state, "loading", lat, lng, now, conn)
    elif new_state == WorkState.UNLOADING:
        await track_segment_service.switch_segment_type(state, "unloading", lat, lng, now, conn)
    elif new_state in (WorkState.TRANSPORT_LOADED, WorkState.TRANSPORT_EMPTY):
        # 仅在从装/卸料段离开时才切换（避免其他转换多开段）
        if old in (WorkState.LOADING, WorkState.UNLOADING):
            await track_segment_service.switch_segment_type(state, None, lat, lng, now, conn)

    # ── 运输超时计时器管理 ────────────────────────────────────────────────────
    if new_state in (WorkState.TRANSPORT_LOADED, WorkState.TRANSPORT_EMPTY):
        state.transport_started_at = now   # 开始计时
    else:
        state.transport_started_at = None  # 抵达目标区或变为未知，停止计时

    await logger.ainfo(
        "work_state_transition",
        device_id=state.device_id,
        vehicle_id=state.vehicle_id,
        old=old,
        new=new_state,
    )
