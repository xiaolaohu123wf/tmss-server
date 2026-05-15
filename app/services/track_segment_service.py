"""
轨迹分段实时服务（v1.2.0）。

每个 GPS 包到达时调用 process_gps_point()，该函数驱动与批处理 SegmentFSM
相同的六态状态机，但在 DeviceState（内存）+ DB（track_segment）上实时操作。

六种段类型（详见 ARCHITECTURE.md §附录E）：
  loading          装料中
  unloading        卸料中
  transport_loaded 重载运输中
  transport_empty  空载中
  unknown          未知状态
  idle             停车（默认隐藏）
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog

from app.core.device_registry import DeviceState
from app.core.enums import WorkState
from app.db.repos.geo_zone_repo import GeoZoneRow
from app.db.repos.track_segment_repo import TrackSegmentRepo
from app.services.segment_resegment_service import IDLE_RADIUS_M, _haversine_m

logger = structlog.get_logger()

_ts_repo = TrackSegmentRepo()

_TRANSPORT_TYPES = frozenset(["transport_loaded", "transport_empty"])
_WORK_ZONE_TYPES = frozenset(["loading", "unloading"])

# WorkState 与 segment_type 的映射
_SEG_TO_WORK_STATE: dict[str, WorkState] = {
    "loading": WorkState.LOADING,
    "unloading": WorkState.UNLOADING,
    "transport_loaded": WorkState.TRANSPORT_LOADED,
    "transport_empty": WorkState.TRANSPORT_EMPTY,
    "unknown": WorkState.UNKNOWN,
    "idle": WorkState.IDLE,
}


async def process_gps_point(
    state: DeviceState,
    lat: float,
    lng: float,
    recorded_at: datetime,
    zones_at_point: list[GeoZoneRow],
    *,
    park_threshold_min: int,
    transport_timeout_min: int,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> None:
    """
    实时 GPS 包处理：更新 DeviceState 中的轨迹段状态并同步到 DB。
    替换旧版 get_or_advance_segment() + work_state_service.update()。
    """
    from app.core.enums import ZoneType
    loading_zone = next(
        (z for z in zones_at_point if z.zone_type == ZoneType.LOADING), None
    )
    unloading_zone = next(
        (z for z in zones_at_point if z.zone_type == ZoneType.UNLOADING), None
    )

    async with state.segment_lock:
        await _process_locked(
            state,
            lat=lat,
            lng=lng,
            recorded_at=recorded_at,
            loading_zone=loading_zone,
            unloading_zone=unloading_zone,
            park_threshold_min=park_threshold_min,
            transport_timeout_min=transport_timeout_min,
            conn=conn,
        )

    # 更新最后已知坐标（无需在锁内）
    state.last_point_at = recorded_at
    state.last_point_lat = lat
    state.last_point_lng = lng


async def _process_locked(
    state: DeviceState,
    *,
    lat: float,
    lng: float,
    recorded_at: datetime,
    loading_zone: Optional[GeoZoneRow],
    unloading_zone: Optional[GeoZoneRow],
    park_threshold_min: int,
    transport_timeout_min: int,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> None:
    active_zone = loading_zone or unloading_zone

    # ── 首次启动或重启恢复 ────────────────────────────────────────────────
    if state.current_segment_id is None:
        await _recover_or_open_unknown(state, lat, lng, recorded_at, conn)
        return  # 本次包直接归入恢复/新建的段

    # ── GPS 时间跳变检测：间隔 ≥ 停车阈值 → 强制切段 ─────────────────────
    if (
        state.last_point_at is not None
        and (recorded_at - state.last_point_at).total_seconds() / 60.0 >= park_threshold_min
    ):
        last_lat = state.last_point_lat or lat
        last_lng = state.last_point_lng or lng
        await _close_segment(
            state, ended_at=state.last_point_at, end_lat=last_lat, end_lng=last_lng, conn=conn
        )
        seg_id = await _ts_repo.open_segment(
            conn,
            device_id=state.device_id,
            started_at=recorded_at,
            start_lat=lat,
            start_lng=lng,
            vehicle_id=state.vehicle_id,
            segment_type="unknown",
        )
        state.current_segment_id = seg_id
        state.current_segment_type = "unknown"
        state.transport_started_at = None
        state.zone_entry_id = None
        state.zone_entry_at = None
        state.zone_entry_lat = None
        state.zone_entry_lng = None
        state.stationary_anchor_lat = lat
        state.stationary_anchor_lng = lng
        state.stationary_since = recorded_at
        await logger.ainfo(
            "segment_time_gap_split",
            device_id=state.device_id,
            seg_id=seg_id,
            gap_min=round((recorded_at - state.last_point_at).total_seconds() / 60.0, 1),
        )
        # 重置后继续处理围栏逻辑（当前包可能已在工作区域）

    # ── 围栏区域逻辑 ──────────────────────────────────────────────────────
    if active_zone:
        zone_type = "loading" if loading_zone else "unloading"

        if state.zone_entry_id != active_zone.id:
            state.zone_entry_id = active_zone.id
            state.zone_entry_at = recorded_at
            state.zone_entry_lat = lat
            state.zone_entry_lng = lng

        # 进入围栏立即确认装/卸料（无驻留等待）
        if (
            state.current_segment_type not in _WORK_ZONE_TYPES
            and state.zone_entry_at is not None
        ):
            entry_at = state.zone_entry_at
            entry_lat = state.zone_entry_lat or lat
            entry_lng = state.zone_entry_lng or lng

            # 回溯关闭前段（结束于 zone_entry_at）
            await _close_segment(state, ended_at=entry_at, end_lat=entry_lat, end_lng=entry_lng, conn=conn)

            # 开启 loading/unloading 段（从 zone_entry_at 开始）
            seg_id = await _ts_repo.open_segment(
                conn,
                device_id=state.device_id,
                started_at=entry_at,
                start_lat=entry_lat,
                start_lng=entry_lng,
                vehicle_id=state.vehicle_id,
                segment_type=zone_type,
            )
            state.current_segment_id = seg_id
            state.current_segment_type = zone_type
            state.transport_started_at = None
            # 进入围栏后清除停车锚点（装/卸料区内不做 idle 检测）
            state.stationary_anchor_lat = None
            state.stationary_anchor_lng = None
            state.stationary_since = None

            await logger.ainfo(
                "segment_dwell_confirmed",
                device_id=state.device_id,
                seg_id=seg_id,
                zone_type=zone_type,
                entry_at=entry_at.isoformat(),
            )

    else:
        # 在围栏外
        if state.current_segment_type in _WORK_ZONE_TYPES:
            # 已确认装/卸料段 → 关闭工作段，开启运输段。
            # 注意：重连恢复开放段时 zone_entry_id 可能为空，不能以其作为唯一切换条件，
            # 否则会出现“已离开装料区但仍保持 loading 颜色”的滞留状态。
            prev = state.current_segment_type
            await _close_segment(state, ended_at=recorded_at, end_lat=lat, end_lng=lng, conn=conn)
            next_type = "transport_loaded" if prev == "loading" else "transport_empty"
            seg_id = await _ts_repo.open_segment(
                conn,
                device_id=state.device_id,
                started_at=recorded_at,
                start_lat=lat,
                start_lng=lng,
                vehicle_id=state.vehicle_id,
                segment_type=next_type,
            )
            state.current_segment_id = seg_id
            state.current_segment_type = next_type
            state.transport_started_at = recorded_at
            # 确认后清除围栏进入计时
            state.zone_entry_id = None
            state.zone_entry_at = None
            state.zone_entry_lat = None
            state.zone_entry_lng = None
            await logger.ainfo(
                "segment_zone_exit",
                device_id=state.device_id,
                seg_id=seg_id,
                next_type=next_type,
            )
        # 未确认驻留的短暂离开：保留 zone_entry_ 状态，下次进入同一围栏时计时继续累积，
        # 防止 GPS 边界抖动导致 zone_entry_at 不断重置而无法触发驻留确认。

        # ── 运输超时检测 ──────────────────────────────────────────────────
        if (
            state.current_segment_type in _TRANSPORT_TYPES
            and state.transport_started_at is not None
            and transport_timeout_min > 0
            and (recorded_at - state.transport_started_at).total_seconds() / 60.0
            >= transport_timeout_min
        ):
            await _ts_repo.update_segment_type(conn, state.current_segment_id, "unknown")  # type: ignore[arg-type]
            state.current_segment_type = "unknown"
            state.transport_started_at = None
            await logger.ainfo(
                "segment_transport_timeout",
                device_id=state.device_id,
                seg_id=state.current_segment_id,
            )

        # ── 停车 / idle 检测 ──────────────────────────────────────────────
        anchor_lat = state.stationary_anchor_lat
        anchor_lng = state.stationary_anchor_lng

        if anchor_lat is None or anchor_lng is None:
            state.stationary_anchor_lat = lat
            state.stationary_anchor_lng = lng
            state.stationary_since = recorded_at
        else:
            dist = _haversine_m(anchor_lat, anchor_lng, lat, lng)
            if dist > IDLE_RADIUS_M:
                # 车辆移动
                if state.current_segment_type == "idle":
                    await _close_segment(state, ended_at=recorded_at, end_lat=lat, end_lng=lng, conn=conn)
                    seg_id = await _ts_repo.open_segment(
                        conn,
                        device_id=state.device_id,
                        started_at=recorded_at,
                        start_lat=lat,
                        start_lng=lng,
                        vehicle_id=state.vehicle_id,
                        segment_type="unknown",
                    )
                    state.current_segment_id = seg_id
                    state.current_segment_type = "unknown"
                    await logger.ainfo("segment_idle_exit", device_id=state.device_id, seg_id=seg_id)
                state.stationary_anchor_lat = lat
                state.stationary_anchor_lng = lng
                state.stationary_since = recorded_at
            else:
                # 仍在停车范围内
                if (
                    state.current_segment_type != "idle"
                    and state.stationary_since is not None
                    and (recorded_at - state.stationary_since).total_seconds() / 60.0
                    >= park_threshold_min
                ):
                    anchor_since = state.stationary_since
                    await _close_segment(
                        state,
                        ended_at=anchor_since,
                        end_lat=lat,
                        end_lng=lng,
                        conn=conn,
                    )
                    seg_id = await _ts_repo.open_segment(
                        conn,
                        device_id=state.device_id,
                        started_at=anchor_since,
                        start_lat=lat,
                        start_lng=lng,
                        vehicle_id=state.vehicle_id,
                        segment_type="idle",
                    )
                    state.current_segment_id = seg_id
                    state.current_segment_type = "idle"
                    await logger.ainfo(
                        "segment_idle_entered",
                        device_id=state.device_id,
                        seg_id=seg_id,
                        since=anchor_since.isoformat(),
                    )

    # ── 更新 work_state ───────────────────────────────────────────────────
    new_ws = _SEG_TO_WORK_STATE.get(state.current_segment_type or "unknown", WorkState.UNKNOWN)
    if state.current_work_state != new_ws:
        await _record_work_state_change(state, new_ws, conn)


async def _close_segment(
    state: DeviceState,
    ended_at: datetime,
    end_lat: float,
    end_lng: float,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> None:
    if state.current_segment_id is not None:
        await _ts_repo.close_segment(
            conn,
            segment_id=state.current_segment_id,
            ended_at=ended_at,
            end_lat=end_lat,
            end_lng=end_lng,
        )
        await logger.adebug(
            "segment_closed",
            device_id=state.device_id,
            seg_id=state.current_segment_id,
            seg_type=state.current_segment_type,
        )


async def _recover_or_open_unknown(
    state: DeviceState,
    lat: float,
    lng: float,
    recorded_at: datetime,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> None:
    """首次包（重启或首连）：尝试恢复 DB 中的开放段，否则新开 unknown 段。"""
    existing = await _ts_repo.find_open_by_device(conn, state.device_id)
    if existing and existing.vehicle_id == state.vehicle_id:
        state.current_segment_id = existing.id
        state.current_segment_type = existing.segment_type or "unknown"
        await logger.ainfo(
            "segment_recovered",
            device_id=state.device_id,
            seg_id=existing.id,
        )
        return

    if existing:
        # 车辆绑定已变，关闭旧段
        await _ts_repo.close_segment(
            conn,
            segment_id=existing.id,
            ended_at=recorded_at,
            end_lat=lat,
            end_lng=lng,
        )

    seg_id = await _ts_repo.open_segment(
        conn,
        device_id=state.device_id,
        started_at=recorded_at,
        start_lat=lat,
        start_lng=lng,
        vehicle_id=state.vehicle_id,
        segment_type="unknown",
    )
    state.current_segment_id = seg_id
    state.current_segment_type = "unknown"
    state.stationary_anchor_lat = lat
    state.stationary_anchor_lng = lng
    state.stationary_since = recorded_at
    await logger.ainfo(
        "segment_opened_unknown",
        device_id=state.device_id,
        seg_id=seg_id,
    )


async def _record_work_state_change(
    state: DeviceState,
    new_ws: WorkState,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> None:
    """记录 work_session 状态变更。"""
    from app.db.repos.work_session_repo import WorkSessionRepo
    _repo = WorkSessionRepo()
    if state.vehicle_id is None:
        state.current_work_state = new_ws
        return
    open_session = await _repo.find_open_by_vehicle(conn, state.vehicle_id)
    if open_session:
        await _repo.close_session(conn, open_session.id)
    zone_id = state.zone_entry_id if new_ws in (WorkState.LOADING, WorkState.UNLOADING) else None
    await _repo.open_session(conn, state.vehicle_id, new_ws, zone_id)
    state.current_work_state = new_ws


# ---------------------------------------------------------------------------
# 兼容旧调用：关闭当前段并立即以新类型开启（work_state_service 曾调用）
# 已被 process_gps_point 内联，此处保留供其他调用方使用
# ---------------------------------------------------------------------------

async def close_on_disconnect(
    state: DeviceState,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> None:
    """设备断线时关闭开放段。"""
    async with state.segment_lock:
        if state.current_segment_id is None:
            return
        now = datetime.now(tz=timezone.utc)
        lat = state.last_point_lat or 0.0
        lng = state.last_point_lng or 0.0
        await _ts_repo.close_segment(
            conn,
            segment_id=state.current_segment_id,
            ended_at=now,
            end_lat=lat,
            end_lng=lng,
        )
        state.current_segment_id = None
        state.current_segment_type = None
