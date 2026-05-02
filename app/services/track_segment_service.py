"""
轨迹分段服务。

每个有效 GPS 包到达时调用 get_or_advance_segment()，
返回当前应使用的 segment_id（确保已在 DB 中建立记录）。

分段规则（满足任一即开新段）：
  1. 时间间隔：上一包与当前包时刻差 ≥ park_threshold_min 分钟
  2. 停车驻留：距最后一次"移动"（位移 > PARK_STATIONARY_RADIUS_M 米）已超 park_threshold_min 分钟
  - 首包：开启新段
  - 否则：续接当前段
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

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
    r = 6_371_000.0  # 地球半径（米）
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
) -> int:
    """
    返回当前有效的 segment_id（int）。
    副作用：更新 state.current_segment_id、state.last_point_at、驻留锚点。
    使用 state.segment_lock 保证同一设备并发 GPS 包不会重复开段。
    """
    async with state.segment_lock:
        return await _get_or_advance_segment_locked(
            state, lat, lng, recorded_at, conn, park_threshold_min
        )


async def _get_or_advance_segment_locked(
    state: DeviceState,
    lat: float,
    lng: float,
    recorded_at: datetime,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    park_threshold_min: int,
) -> int:
    now = recorded_at

    if state.current_segment_id is None:
        # 服务重启或短暂断线重连后，从 DB 恢复开放段
        existing = await _ts_repo.find_open_by_device(conn, state.device_id)
        if existing:
            if existing.vehicle_id == state.vehicle_id:
                # 车辆绑定未变，续接旧段
                state.current_segment_id = existing.id
                # 取该段最后一个定位点的时间，作为时间差计算基准
                # （不能用 started_at，否则 Rule 2 会把整段历史时间都算进去）
                last_ts = await conn.fetchval(
                    "SELECT recorded_at FROM location_point"
                    " WHERE segment_id = $1 ORDER BY recorded_at DESC LIMIT 1",
                    existing.id,
                )
                state.last_point_at = last_ts if last_ts is not None else existing.started_at
            else:
                # 车辆绑定已变更，关闭旧段，下方逻辑会开新段
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

    # ── 规则 3：停车驻留分段（位移半径 < PARK_STATIONARY_RADIUS_M） ───────────
    if not need_new and state.current_segment_id is not None:
        anchor_lat = state.stationary_anchor_lat
        anchor_lng = state.stationary_anchor_lng

        if anchor_lat is None or anchor_lng is None:
            # 初始化锚点
            state.stationary_anchor_lat = lat
            state.stationary_anchor_lng = lng
            state.stationary_since = now
        else:
            dist = _distance_m(anchor_lat, anchor_lng, lat, lng)
            if dist > PARK_STATIONARY_RADIUS_M:
                # 设备移动了，更新锚点
                state.stationary_anchor_lat = lat
                state.stationary_anchor_lng = lng
                state.stationary_since = now
            else:
                # 设备在锚点附近（停车中），检查驻留时长
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
        # 关闭旧段（如存在）
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
        )
        state.current_segment_id = seg_id
        await logger.ainfo(
            "track_segment_opened",
            device_id=state.device_id,
            segment_id=seg_id,
        )

        # 新段开启：重置驻留锚点
        state.stationary_anchor_lat = lat
        state.stationary_anchor_lng = lng
        state.stationary_since = now

    else:
        await _ts_repo.increment_points(conn, state.current_segment_id)  # type: ignore[arg-type]

    state.last_point_at = now
    return state.current_segment_id  # type: ignore[return-value]
