"""
轨迹分段服务。

每个有效 GPS 包到达时调用 get_or_advance_segment()，
返回当前应使用的 segment_id（确保已在 DB 中建立记录）。

分段规则（满足任一即开新段）：
  1. 时间间隔：上一包与当前包时刻差 ≥ park_threshold_min 分钟
  2. 停车驻留：距最后一次"移动"（位移 > PARK_STATIONARY_RADIUS_M 米）已超 park_threshold_min 分钟
     ⚠ 当 suppress_stationary_split=True 时跳过规则 2（装/卸料状态下保持一条段）
  - 首包：开启新段
  - 否则：续接当前段

特殊操作：
  switch_segment_type() — 工作状态切换时（装/卸料开始/结束）调用，
  关闭当前段并开启指定类型的新段，同步更新 DeviceState。
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog

from app.core.device_registry import DeviceState
from app.db.repos.track_segment_repo import TrackSegmentRepo

logger = structlog.get_logger()

_ts_repo = TrackSegmentRepo()

# 停车半径阈值（米）：设备在此半径内 park_threshold_min 分钟即视为停车
PARK_STATIONARY_RADIUS_M = 10.0


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine 距离（米），适用于短距离（误差 < 0.1%）。"""
    r = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


async def get_or_advance_segment(
    state: DeviceState,
    lat: float,
    lng: float,
    recorded_at: datetime,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    park_threshold_min: int,
    suppress_stationary_split: bool = False,
) -> int:
    """
    返回当前有效的 segment_id（int）。
    suppress_stationary_split=True 时跳过规则 2（装/卸料期间不按驻留切段）。
    """
    async with state.segment_lock:
        return await _get_or_advance_segment_locked(
            state, lat, lng, recorded_at, conn, park_threshold_min, suppress_stationary_split
        )


async def _get_or_advance_segment_locked(
    state: DeviceState,
    lat: float,
    lng: float,
    recorded_at: datetime,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    park_threshold_min: int,
    suppress_stationary_split: bool,
) -> int:
    now = recorded_at

    if state.current_segment_id is None:
        # 服务重启或短暂断线重连后，从 DB 恢复开放段
        existing = await _ts_repo.find_open_by_device(conn, state.device_id)
        if existing:
            if existing.vehicle_id == state.vehicle_id:
                state.current_segment_id = existing.id
                state.current_segment_type = existing.segment_type
                last_ts = await conn.fetchval(
                    "SELECT recorded_at FROM location_point"
                    " WHERE segment_id = $1 ORDER BY recorded_at DESC LIMIT 1",
                    existing.id,
                )
                state.last_point_at = last_ts if last_ts is not None else existing.started_at
            else:
                end_lat = existing.start_lat or lat
                end_lng = existing.start_lng or lng
                await _ts_repo.close_segment(
                    conn,
                    segment_id=existing.id,
                    ended_at=now,
                    end_lat=end_lat,
                    end_lng=end_lng,
                )
                await logger.ainfo(
                    "track_segment_closed_vehicle_changed",
                    device_id=state.device_id,
                    segment_id=existing.id,
                    old_vehicle_id=existing.vehicle_id,
                    new_vehicle_id=state.vehicle_id,
                )

    need_new = False

    # ── 规则 1：无当前段（首包） ──────────────────────────────────────────────
    if state.current_segment_id is None:
        need_new = True

    # ── 规则 2：时间间隔分段 ──────────────────────────────────────────────────
    elif state.last_point_at is not None:
        gap_min = (now - state.last_point_at).total_seconds() / 60.0
        if gap_min >= park_threshold_min:
            need_new = True
            await logger.adebug(
                "segment_split_time_gap",
                device_id=state.device_id,
                gap_min=round(gap_min, 1),
            )

    # ── 规则 3：停车驻留分段（suppress_stationary_split=True 时跳过）────────
    if not need_new and not suppress_stationary_split and state.current_segment_id is not None:
        anchor_lat = state.stationary_anchor_lat
        anchor_lng = state.stationary_anchor_lng

        if anchor_lat is None or anchor_lng is None:
            state.stationary_anchor_lat = lat
            state.stationary_anchor_lng = lng
            state.stationary_since = now
        else:
            dist = _distance_m(anchor_lat, anchor_lng, lat, lng)
            if dist > PARK_STATIONARY_RADIUS_M:
                state.stationary_anchor_lat = lat
                state.stationary_anchor_lng = lng
                state.stationary_since = now
            else:
                if state.stationary_since is not None:
                    parked_min = (now - state.stationary_since).total_seconds() / 60.0
                    if parked_min >= park_threshold_min:
                        need_new = True
                        await logger.adebug(
                            "segment_split_stationary",
                            device_id=state.device_id,
                            parked_min=round(parked_min, 1),
                            radius_m=round(dist, 1),
                        )

    # ── 执行分段 ──────────────────────────────────────────────────────────────
    if need_new:
        if state.current_segment_id is not None and state.last_point_at is not None:
            await _ts_repo.close_segment(
                conn,
                segment_id=state.current_segment_id,
                ended_at=state.last_point_at,
                end_lat=lat,
                end_lng=lng,
            )
            await logger.ainfo(
                "track_segment_closed",
                device_id=state.device_id,
                segment_id=state.current_segment_id,
            )

        seg_id = await _ts_repo.open_segment(
            conn,
            device_id=state.device_id,
            started_at=now,
            start_lat=lat,
            start_lng=lng,
            vehicle_id=state.vehicle_id,
            segment_type=None,  # 普通段；类型段由 switch_segment_type 开启
        )
        state.current_segment_id = seg_id
        state.current_segment_type = None
        await logger.ainfo(
            "track_segment_opened",
            device_id=state.device_id,
            segment_id=seg_id,
        )

        state.stationary_anchor_lat = lat
        state.stationary_anchor_lng = lng
        state.stationary_since = now

    else:
        await _ts_repo.increment_points(conn, state.current_segment_id)  # type: ignore[arg-type]

    state.last_point_at = now
    return state.current_segment_id  # type: ignore[return-value]


async def switch_segment_type(
    state: DeviceState,
    new_type: Optional[str],
    lat: float,
    lng: float,
    now: datetime,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> int:
    """
    关闭当前段，立即开启类型为 new_type 的新段。
    new_type: 'loading' | 'unloading' | None（None=普通行驶段）

    在 work_state_service 作业状态转换时调用；使用 segment_lock 避免并发问题。
    """
    async with state.segment_lock:
        # 关闭当前段
        if state.current_segment_id is not None and state.last_point_at is not None:
            await _ts_repo.close_segment(
                conn,
                segment_id=state.current_segment_id,
                ended_at=now,
                end_lat=lat,
                end_lng=lng,
            )
            await logger.ainfo(
                "track_segment_closed_for_type_switch",
                device_id=state.device_id,
                segment_id=state.current_segment_id,
                old_type=state.current_segment_type,
                new_type=new_type,
            )

        # 开启新段
        seg_id = await _ts_repo.open_segment(
            conn,
            device_id=state.device_id,
            started_at=now,
            start_lat=lat,
            start_lng=lng,
            vehicle_id=state.vehicle_id,
            segment_type=new_type,
        )
        state.current_segment_id = seg_id
        state.current_segment_type = new_type
        state.last_point_at = now
        # 重置驻留锚点（新段开始位置作为新锚点）
        state.stationary_anchor_lat = lat
        state.stationary_anchor_lng = lng
        state.stationary_since = now

        await logger.ainfo(
            "track_segment_type_switched",
            device_id=state.device_id,
            segment_id=seg_id,
            segment_type=new_type,
        )
        return seg_id
