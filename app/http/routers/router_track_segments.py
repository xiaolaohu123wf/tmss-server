from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

_log = structlog.get_logger()

from app.cache.session_repo import SessionData
from app.core.enums import UserRole
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.db.deps import get_db_conn
from app.db.repos.track_query_repo import TrackQueryRepo
from app.http.deps import require_fleet_or_above, require_manager
from app.http.response import ok
from app.services.geofence_service import (
    get_enabled_zones,
    wgs84_to_gcj02,
    zone_name_at,
)

router = APIRouter(prefix="/api/track-segments", tags=["track-segments"])
_repo = TrackQueryRepo()

_TRANSPORT_TYPES = frozenset(["transport_loaded", "transport_empty"])
_TRANSPORT_BUFFER_MIN = 3  # 运输段两端各扩展 3 分钟，展示完整驶入/驶出轨迹

# 单次查询最大时间跨度：防止超大窗口一次性拉取全部历史数据撑爆内存和 DB
_MAX_QUERY_DAYS = 31

# distance_km 降级计算上限：历史段或回填未完成时，每次请求最多实时计算 N 条；
# 超出部分暂显示 0.0，后台回填完成后自动恢复正常值。
_FALLBACK_DIST_CAP = 20


def _fleet_filter(session: SessionData) -> Optional[int]:
    return None if session.role == UserRole.MANAGER else session.fleet_id


async def _ensure_segment_access(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    segment_id: int,
    session: SessionData,
) -> None:
    row = await conn.fetchrow(
        """
        SELECT ts.vehicle_id, v.fleet_id
        FROM track_segment ts
        LEFT JOIN vehicle v ON v.id = ts.vehicle_id AND v.deleted_at IS NULL
        WHERE ts.id = $1
        """,
        segment_id,
    )
    if row is None:
        raise NotFoundError("轨迹段不存在")
    if row["vehicle_id"] is None:
        if session.role != UserRole.MANAGER:
            raise PermissionDeniedError("无权访问该轨迹")
        return
    fleet_id = row["fleet_id"]
    if session.role == UserRole.FLEET_CAPTAIN and fleet_id != session.fleet_id:
        raise PermissionDeniedError("无权访问其他车队数据")


class TrackSegmentListItem(BaseModel):
    """起终点坐标为 GCJ-02，与高德一致。
    start/end loc_type 在 V011 后统一视为 WGS-84 处理（起终点由 GPS 触发，LBS 偏差在列表视图可接受）。
    """

    id: int
    vehicle_id: Optional[int]
    license_plate: Optional[str]
    started_at: str
    ended_at: Optional[str]
    distance_km: float
    segment_type: Optional[str] = None
    start_zone_name: Optional[str]
    end_zone_name: Optional[str]
    cargo_name: Optional[str] = None
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    end_lat: Optional[float] = None
    end_lng: Optional[float] = None
    buffer_min: int = 0  # 前端查询 points 时应附带的缓冲分钟数


class TrackPointItem(BaseModel):
    """单点坐标为 GCJ-02（火星坐标），与高德地图底图一致。"""

    recorded_at: str
    lat: float
    lng: float
    speed: Optional[float]
    loc_type: str


def _to_amap_latlng(lat: float, lng: float, loc_type: str) -> tuple[float, float]:
    """库内为设备原始坐标：GPS=WGS-84；LBS 在国内多为 GCJ-02，不再二次偏移。"""
    if loc_type == "lbs":
        return lat, lng
    return wgs84_to_gcj02(lat, lng)


@router.get("")
async def list_track_segments(
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
    from_: datetime = Query(..., alias="from"),
    to: datetime = Query(..., alias="to"),
    vehicle_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(200, ge=1, le=500),
    min_distance_km: float = Query(
        0.3,
        ge=0.0,
        description="过滤掉行驶距离小于该值（km）的 unknown 段；传 0 可显示全部",
    ),
    show_idle: bool = Query(
        False,
        description="是否显示停车段（idle）；默认隐藏",
    ),
) -> dict:
    if to <= from_:
        return ok([])

    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    # ── 查询窗口上限：防止超宽时间范围拉爆内存和 DB ───────────────────────────
    range_days = (to - from_).total_seconds() / 86400.0
    if range_days > _MAX_QUERY_DAYS:
        raise ValidationError(f"查询范围不能超过 {_MAX_QUERY_DAYS} 天，当前为 {range_days:.1f} 天")

    ff = _fleet_filter(session)
    internal_limit = min(limit * 4, 500)

    t0 = time.perf_counter()
    rows = await _repo.list_segments(
        conn,
        started_from=from_,
        started_to=to,
        vehicle_id=vehicle_id,
        fleet_id=ff,
        limit=internal_limit,
    )
    t_list = time.perf_counter() - t0

    # ── 距离：优先使用 V011 预计算列，仅对 NULL 已关闭段降级实时计算 ──────────
    # 开放段（ended_at IS NULL）跳过：用 COALESCE(ended_at, NOW()) 会扫描几十
    # 小时的 location_point，是本次 ~900ms 卡顿的直接根源。开放段关闭时
    # COMPUTE_DISTANCE_SQL 会自动填入真实值，列表中暂显示 0.0 即可。
    null_closed_ids = [r.id for r in rows if r.distance_km is None and r.ended_at is not None]
    capped_ids = null_closed_ids[:_FALLBACK_DIST_CAP]
    t1 = time.perf_counter()
    fallback_dist: dict[int, float] = (
        await _repo.distance_km_for_segments(conn, capped_ids) if capped_ids else {}
    )
    t_dist = time.perf_counter() - t1

    # ── 围栏标签：加载一次缓存列表，在内存中做纯 Python 点在多边形判定 ────────
    t2 = time.perf_counter()
    zones = await get_enabled_zones(conn)
    t_zones = time.perf_counter() - t2
    t3 = time.perf_counter()

    items: list[dict] = []
    for r in rows:
        distance_km = round(
            r.distance_km if r.distance_km is not None else fallback_dist.get(r.id, 0.0),
            3,
        )

        # idle 段默认隐藏（用户切换"显示停车记录"时传 show_idle=true）
        if r.segment_type == "idle" and not show_idle:
            continue

        # unknown 段按距离过滤（短暂停车/原地驻留噪点）
        if (
            r.ended_at is not None
            and r.segment_type in ("unknown", None)
            and distance_km < min_distance_km
        ):
            continue

        s_lat, s_lng = r.start_lat, r.start_lng
        # 开放段 end_lat/lng 为 NULL；列表视图不展示终点，前端以"进行中"标签区分
        e_lat, e_lng = r.end_lat, r.end_lng

        # 同步 O(围栏数) 点在多边形，无 await
        start_zone = zone_name_at(zones, s_lat, s_lng)
        end_zone = zone_name_at(zones, e_lat, e_lng)

        # 起终点坐标从 track_segment 存储列读取（GPS 触发写入，视为 WGS-84）→ GCJ-02
        map_s_lat, map_s_lng = (
            wgs84_to_gcj02(s_lat, s_lng)
            if s_lat is not None and s_lng is not None
            else (None, None)
        )
        map_e_lat, map_e_lng = (
            wgs84_to_gcj02(e_lat, e_lng)
            if e_lat is not None and e_lng is not None
            else (None, None)
        )

        buf = _TRANSPORT_BUFFER_MIN if r.segment_type in _TRANSPORT_TYPES else 0

        item = TrackSegmentListItem(
            id=r.id,
            vehicle_id=r.vehicle_id,
            license_plate=r.license_plate,
            started_at=r.started_at.isoformat(),
            ended_at=r.ended_at.isoformat() if r.ended_at else None,
            distance_km=distance_km,
            segment_type=r.segment_type,
            start_zone_name=start_zone,
            end_zone_name=end_zone,
            cargo_name=None,
            start_lat=map_s_lat,
            start_lng=map_s_lng,
            end_lat=map_e_lat,
            end_lng=map_e_lng,
            buffer_min=buf,
        )
        items.append(item.model_dump())
        if len(items) >= limit:
            break

    t_loop = time.perf_counter() - t3
    t_total = time.perf_counter() - t0
    await _log.ainfo(
        "track_segments_list_perf",
        rows_fetched=len(rows),
        items_returned=len(items),
        null_dist_total=len(null_closed_ids),
        null_dist_computed=len(capped_ids),
        t_list_ms=round(t_list * 1000, 1),
        t_dist_ms=round(t_dist * 1000, 1),
        t_zones_ms=round(t_zones * 1000, 1),
        t_total_ms=round(t_total * 1000, 1),
    )
    return ok(items)


@router.get("/{segment_id}/points")
async def get_segment_points(
    segment_id: int,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
    limit: int = Query(25000, ge=100, le=50000),
    buffer_min: int = Query(
        0,
        ge=0,
        le=30,
        description="运料/空载段两端时间缓冲（分钟）；传 3 时前后各扩展 3 分钟轨迹",
    ),
) -> dict:
    await _ensure_segment_access(conn, segment_id, session)
    pts = await _repo.list_points(conn, segment_id, max_points=limit, buffer_min=buffer_min)
    data = []
    for p in pts:
        mlat, mlng = _to_amap_latlng(p.lat, p.lng, p.loc_type)
        data.append(
            TrackPointItem(
                recorded_at=p.recorded_at.isoformat(),
                lat=mlat,
                lng=mlng,
                speed=p.speed,
                loc_type=p.loc_type,
            ).model_dump()
        )
    return ok(data)


@router.delete("/{segment_id}")
async def delete_track_segment(
    segment_id: int,
    _session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """管理员删除轨迹段记录（v1.2.0：定位点独立存储，段删除不影响原始点）。"""
    row = await conn.fetchrow("SELECT 1 FROM track_segment WHERE id = $1", segment_id)
    if row is None:
        raise NotFoundError("轨迹段不存在")
    deleted = await _repo.delete_segment(conn, segment_id)
    if not deleted:
        raise NotFoundError("轨迹段不存在")
    return ok(None)
