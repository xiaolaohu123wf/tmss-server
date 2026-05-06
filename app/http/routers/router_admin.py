from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from asyncpg import UniqueViolationError
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.cache.session_repo import SessionData
from app.core.enums import UserRole
from app.core.exceptions import NotFoundError, ValidationError
from app.db.deps import get_db_conn
from app.db.repos.business_config_repo import BusinessConfigRepo, BusinessConfigRow
from app.db.repos.fleet_repo import FleetRepo
from app.db.repos.user_repo import UserRepo
from app.http.deps import require_fleet_or_above, require_manager, require_password_confirm
from app.http.response import ok
from app.tcp.connection import invalidate_gps_handler

router = APIRouter(prefix="/api/admin", tags=["admin"])
_fleet_repo = FleetRepo()
_user_repo = UserRepo()
_business_config_repo = BusinessConfigRepo()


class BusinessConfigPayload(BaseModel):
    """与前端 Settings 表单一致；库字段 loading_dwell_min 在此映射为 loading_min_stay_s。"""

    global_speed_limit: int = Field(ge=10, le=200)
    park_threshold_min: int = Field(ge=1, le=60)
    alert_cooldown_s: int = Field(ge=1, le=300)
    hb_timeout_s: int = Field(ge=30, le=600)
    loading_min_stay_s: int = Field(ge=0, le=3600)
    unloading_min_stay_s: int = Field(ge=0, le=3600)
    weather_city: str = Field(min_length=1, max_length=50)
    map_center_lng: float = Field(ge=-180, le=180)
    map_center_lat: float = Field(ge=-90, le=90)
    transport_timeout_min: int = Field(ge=0, le=480)

    def to_repo_kwargs(self) -> dict[str, int | str | float]:
        return {
            "global_speed_limit": self.global_speed_limit,
            "park_threshold_min": self.park_threshold_min,
            "loading_dwell_min": self.loading_min_stay_s,
            "unloading_dwell_min": self.unloading_min_stay_s,
            "alert_cooldown_s": self.alert_cooldown_s,
            "hb_timeout_s": self.hb_timeout_s,
            "weather_city": self.weather_city,
            "map_center_lng": self.map_center_lng,
            "map_center_lat": self.map_center_lat,
            "transport_timeout_min": self.transport_timeout_min,
        }


class MapCenterPayload(BaseModel):
    """地图默认中心点，供所有已登录用户读取。"""

    map_center_lng: float
    map_center_lat: float


def _payload_from_row(row: BusinessConfigRow) -> BusinessConfigPayload:
    return BusinessConfigPayload(
        global_speed_limit=row.global_speed_limit,
        park_threshold_min=row.park_threshold_min,
        alert_cooldown_s=row.alert_cooldown_s,
        hb_timeout_s=row.hb_timeout_s,
        loading_min_stay_s=row.loading_dwell_min,
        unloading_min_stay_s=row.unloading_dwell_min,
        weather_city=row.weather_city,
        map_center_lng=row.map_center_lng,
        map_center_lat=row.map_center_lat,
        transport_timeout_min=row.transport_timeout_min,
    )


class FleetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    notes: Optional[str] = None
    captain_username: Optional[str] = Field(default=None, min_length=2, max_length=50)


class FleetUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    notes: Optional[str] = None


class FleetResponse(BaseModel):
    id: int
    name: str
    notes: Optional[str]


class FleetCaptainCredentials(BaseModel):
    username: str
    initial_password: str


class FleetCreateResponse(BaseModel):
    id: int
    name: str
    notes: Optional[str]
    captain: FleetCaptainCredentials


_WEATHER_NAMES = ["晴", "多云", "阴", "小雨", "大雨", "雪", "雾", "雷暴"]


@router.get("/weather")
async def get_weather(
    _session: SessionData = Depends(require_fleet_or_above),
) -> dict:
    """返回当前缓存天气（与下发给设备的内容一致），未缓存时返回 null。"""
    from app.cache.pool import get_redis
    from app.cache.weather_cache import WeatherCache

    cached = await WeatherCache().get(get_redis())
    if not cached or ":" not in cached:
        return ok(None)
    temp_str, code_str = cached.split(":", 1)
    try:
        code = int(code_str)
    except ValueError:
        return ok(None)
    name = _WEATHER_NAMES[code] if 0 <= code < len(_WEATHER_NAMES) else "未知"
    return ok({"temp": temp_str, "code": code, "name": name})


@router.get("/map-config")
async def get_map_config(
    _session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """返回地图默认中心点，供大屏、历史轨迹等页面初始化时调用。所有已登录用户可访问。"""
    row = await _business_config_repo.get_singleton(conn)
    if row is None:
        return ok({"map_center_lng": 109.4753, "map_center_lat": 30.2832})
    return ok(MapCenterPayload(
        map_center_lng=row.map_center_lng,
        map_center_lat=row.map_center_lat,
    ).model_dump())


@router.get("/config")
async def get_business_config(
    _session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    row = await _business_config_repo.get_singleton(conn)
    if row is None:
        raise NotFoundError("业务配置不存在")
    return ok(_payload_from_row(row).model_dump())


@router.post("/config")
async def update_business_config(
    body: BusinessConfigPayload,
    _session: SessionData = Depends(require_password_confirm),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    await _business_config_repo.update_singleton(conn, **body.to_repo_kwargs())
    invalidate_gps_handler()
    row = await _business_config_repo.get_singleton(conn)
    if row is None:
        raise NotFoundError("业务配置不存在")
    return ok(_payload_from_row(row).model_dump())


@router.get("/fleets")
async def list_fleets(
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    rows = await _fleet_repo.find_all(conn)
    return ok([FleetResponse(id=r.id, name=r.name, notes=r.notes).model_dump() for r in rows])


@router.post("/fleets")
async def create_fleet(
    body: FleetCreateRequest,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    existing = await _fleet_repo.find_by_name(conn, body.name)
    if existing is not None:
        raise ValidationError("车队名称已存在")

    year = datetime.now(tz=timezone.utc).year

    try:
        async with conn.transaction():
            new_id = await _fleet_repo.create(conn, name=body.name, notes=body.notes)

            # 生成车队长用户名（优先使用传入值，否则用 fleet_{id}）
            candidate = body.captain_username or f"fleet_{new_id}"
            # 如果用户名已被占用，强制回退到 fleet_{id}
            if body.captain_username:
                dup = await _user_repo.find_by_username(conn, candidate)
                if dup is not None:
                    candidate = f"fleet_{new_id}"

            initial_password = f"Fleet@{year}#{new_id}"
            await _user_repo.create(
                conn,
                username=candidate,
                plain_password=initial_password,
                role=UserRole.FLEET_CAPTAIN,
                fleet_id=new_id,
            )
    except UniqueViolationError:
        raise ValidationError("车队名称已存在（含已删除的历史车队），请使用其他名称")

    row = await _fleet_repo.find_by_id(conn, new_id)
    assert row is not None
    return ok(
        FleetCreateResponse(
            id=row.id,
            name=row.name,
            notes=row.notes,
            captain=FleetCaptainCredentials(
                username=candidate,
                initial_password=initial_password,
            ),
        ).model_dump()
    )


@router.put("/fleets/{fleet_id}")
async def update_fleet(
    fleet_id: int,
    body: FleetUpdateRequest,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    row = await _fleet_repo.find_by_id(conn, fleet_id)
    if row is None:
        raise NotFoundError("车队不存在")
    if body.name and body.name != row.name:
        dup = await _fleet_repo.find_by_name(conn, body.name)
        if dup is not None and dup.id != fleet_id:
            raise ValidationError("车队名称已存在")
    await _fleet_repo.update(conn, fleet_id, name=body.name, notes=body.notes)
    updated = await _fleet_repo.find_by_id(conn, fleet_id)
    assert updated is not None
    return ok(FleetResponse(id=updated.id, name=updated.name, notes=updated.notes).model_dump())


@router.delete("/fleets/{fleet_id}")
async def delete_fleet(
    fleet_id: int,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    row = await _fleet_repo.find_by_id(conn, fleet_id)
    if row is None:
        raise NotFoundError("车队不存在")
    await _fleet_repo.soft_delete(conn, fleet_id)
    return ok({"message": "车队已删除"})


@router.post("/reanalyze-segments")
async def reanalyze_segments(
    days: int = 30,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """
    轻量版：仅对已有轨迹段进行装/卸料类型标注（不重建段）。
    仅当起点在围栏内 **且** 持续时长 >= 对应区域的最低停留阈值时才打标签，
    避免将短暂路过或原地驻留（<300 s）误判为装/卸料。
    """
    import math as _math
    from app.core.enums import ZoneType
    from app.services.geofence_service import _load_zones, point_in_polygon, wgs84_to_gcj02

    cfg = await _business_config_repo.get_singleton(conn)
    loading_dwell_s = (cfg.loading_dwell_min if cfg else 300) * 60
    unloading_dwell_s = (cfg.unloading_dwell_min if cfg else 180) * 60

    zones = await _load_zones(conn)
    loading_zones = [z for z in zones if z.zone_type == ZoneType.LOADING]
    unloading_zones = [z for z in zones if z.zone_type == ZoneType.UNLOADING]

    if not loading_zones and not unloading_zones:
        return ok({"labeled": 0, "total_checked": 0, "message": "未发现已启用的取土/弃土围栏"})

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await conn.fetch(
        """
        SELECT id, start_lat, start_lng, started_at, ended_at
        FROM track_segment
        WHERE started_at >= $1
          AND ended_at IS NOT NULL
          AND segment_type IS NULL
          AND start_lat IS NOT NULL
          AND start_lng IS NOT NULL
        """,
        cutoff,
    )

    labeled = 0
    for row in rows:
        duration_s = (row["ended_at"] - row["started_at"]).total_seconds()
        lat_gcj, lng_gcj = wgs84_to_gcj02(float(row["start_lat"]), float(row["start_lng"]))
        seg_type: Optional[str] = None

        for z in loading_zones:
            if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
                if duration_s >= loading_dwell_s:
                    seg_type = "loading"
                break
        if seg_type is None:
            for z in unloading_zones:
                if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
                    if duration_s >= unloading_dwell_s:
                        seg_type = "unloading"
                    break

        if seg_type:
            await conn.execute(
                "UPDATE track_segment SET segment_type = $1 WHERE id = $2",
                seg_type,
                int(row["id"]),
            )
            labeled += 1

    return ok({"labeled": labeled, "total_checked": len(rows)})


@router.post("/resegment-history")
async def resegment_history(
    days: int = 7,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """
    重量级历史轨迹重分割：从原始定位点重建轨迹段。
    分割规则：
      1. 相邻两点时间间隔 > park_threshold_min → 强制断段
      2. 点位进入/离开装料/卸料围栏 → 在边界处断段
    标注规则：
      段起点在围栏内 **且** 段持续时长 >= 对应区域 dwell_min → 标记 loading/unloading。
    操作：删除范围内旧 track_segment，重新创建并更新 location_point.segment_id。
    """
    import math as _math
    from app.core.enums import ZoneType
    from app.services.geofence_service import _load_zones, point_in_polygon, wgs84_to_gcj02

    cfg = await _business_config_repo.get_singleton(conn)
    park_threshold_s: float = (cfg.park_threshold_min if cfg else 10) * 60
    loading_dwell_s: float = (cfg.loading_dwell_min if cfg else 5) * 60
    unloading_dwell_s: float = (cfg.unloading_dwell_min if cfg else 3) * 60

    zones = await _load_zones(conn)
    loading_zones = [z for z in zones if z.zone_type == ZoneType.LOADING]
    unloading_zones = [z for z in zones if z.zone_type == ZoneType.UNLOADING]

    def _check_zone(lat_wgs: float, lng_wgs: float) -> Optional[str]:
        lat_gcj, lng_gcj = wgs84_to_gcj02(lat_wgs, lng_wgs)
        for z in loading_zones:
            if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
                return "loading"
        for z in unloading_zones:
            if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
                return "unloading"
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # 找出范围内有定位数据的所有设备
    device_rows = await conn.fetch(
        "SELECT DISTINCT device_id FROM location_point WHERE recorded_at >= $1",
        cutoff,
    )

    total_created = 0
    total_devices = len(device_rows)

    for dev_row in device_rows:
        device_id = int(dev_row["device_id"])

        # 删除该设备在范围内的旧轨迹段（先解除 location_point 关联）
        old_seg_ids = [
            int(r["id"])
            for r in await conn.fetch(
                "SELECT id FROM track_segment WHERE device_id = $1 AND started_at >= $2",
                device_id,
                cutoff,
            )
        ]
        if old_seg_ids:
            await conn.execute(
                "UPDATE location_point SET segment_id = NULL"
                " WHERE segment_id = ANY($1::BIGINT[]) AND recorded_at >= $2",
                old_seg_ids,
                cutoff,
            )
            await conn.execute(
                "DELETE FROM track_segment WHERE id = ANY($1::BIGINT[])",
                old_seg_ids,
            )

        # 拉取该设备范围内所有定位点（按时间正序）
        pts = await conn.fetch(
            """
            SELECT id, vehicle_id, recorded_at,
                   lat::DOUBLE PRECISION AS lat,
                   lng::DOUBLE PRECISION AS lng
            FROM location_point
            WHERE device_id = $1 AND recorded_at >= $2
            ORDER BY recorded_at ASC, id ASC
            """,
            device_id,
            cutoff,
        )
        if not pts:
            continue

        # ── 分段 Walk ────────────────────────────────────────────────
        # 每个 pending segment 为 list of point records
        segments: list[tuple[list, Optional[str]]] = []   # (pts_list, zone_type_at_start)
        cur_pts: list = [pts[0]]
        cur_zone: Optional[str] = _check_zone(float(pts[0]["lat"]), float(pts[0]["lng"]))

        for i in range(1, len(pts)):
            p = pts[i]
            gap_s = (p["recorded_at"] - pts[i - 1]["recorded_at"]).total_seconds()
            this_zone = _check_zone(float(p["lat"]), float(p["lng"]))

            # 强制断段条件：时间间隔超阈值 or 围栏区域发生变化
            if gap_s > park_threshold_s or this_zone != cur_zone:
                segments.append((cur_pts, cur_zone))
                cur_pts = [p]
                cur_zone = this_zone
            else:
                cur_pts.append(p)

        segments.append((cur_pts, cur_zone))

        # ── 插入新轨迹段 ─────────────────────────────────────────────
        for seg_pts, zone_type in segments:
            if not seg_pts:
                continue

            started_at = seg_pts[0]["recorded_at"]
            ended_at = seg_pts[-1]["recorded_at"]
            start_lat = float(seg_pts[0]["lat"])
            start_lng = float(seg_pts[0]["lng"])
            end_lat = float(seg_pts[-1]["lat"])
            end_lng = float(seg_pts[-1]["lng"])
            duration_s = (ended_at - started_at).total_seconds()

            # vehicle_id：取最后一个点的绑定（覆盖范围内绑定的最新值）
            vehicle_id: Optional[int] = None
            for p in reversed(seg_pts):
                if p["vehicle_id"] is not None:
                    vehicle_id = int(p["vehicle_id"])
                    break

            # 仅当在围栏内且持续时间满足阈值时才打标签
            seg_type: Optional[str] = None
            if zone_type == "loading" and duration_s >= loading_dwell_s:
                seg_type = "loading"
            elif zone_type == "unloading" and duration_s >= unloading_dwell_s:
                seg_type = "unloading"

            seg_id: int = await conn.fetchval(
                """
                INSERT INTO track_segment
                    (device_id, vehicle_id, started_at, ended_at,
                     start_lat, start_lng, end_lat, end_lng,
                     point_count, segment_type)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                RETURNING id
                """,
                device_id, vehicle_id, started_at, ended_at,
                start_lat, start_lng, end_lat, end_lng,
                len(seg_pts), seg_type,
            )

            # 批量更新 location_point.segment_id
            pt_ids = [int(p["id"]) for p in seg_pts]
            await conn.execute(
                "UPDATE location_point SET segment_id = $1"
                " WHERE id = ANY($2::BIGINT[]) AND recorded_at >= $3",
                seg_id, pt_ids, cutoff,
            )
            total_created += 1

    return ok({"segments_created": total_created, "devices_processed": total_devices})
