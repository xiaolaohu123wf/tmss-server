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
    轻量版：对已有轨迹段按「起终点围栏对」重新标注类型。

    标注规则（优先级最高）：
      - 起点在取土区（loading）且终点在弃土区（unloading）→ 装料（loaded run）
      - 起点在弃土区（unloading）且终点在取土区（loading）→ 卸料（empty return）
      - 起终点相同围栏 / 仅一端在围栏 / 均不在围栏 → 不标注（NULL）

    同时清除范围内已有的错误标注，重新按上述规则打标。
    """
    from app.core.enums import ZoneType
    from app.services.geofence_service import _load_zones, point_in_polygon, wgs84_to_gcj02

    zones = await _load_zones(conn)
    loading_zones = [z for z in zones if z.zone_type == ZoneType.LOADING]
    unloading_zones = [z for z in zones if z.zone_type == ZoneType.UNLOADING]

    if not loading_zones and not unloading_zones:
        return ok({"labeled": 0, "total_checked": 0, "message": "未发现已启用的取土/弃土围栏"})

    def _zone_type(lat_wgs: float, lng_wgs: float) -> Optional[str]:
        lat_g, lng_g = wgs84_to_gcj02(lat_wgs, lng_wgs)
        for z in loading_zones:
            if z.coordinates and point_in_polygon(lat_g, lng_g, z.coordinates):
                return "loading"
        for z in unloading_zones:
            if z.coordinates and point_in_polygon(lat_g, lng_g, z.coordinates):
                return "unloading"
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # 查取所有已结束的段（含之前错误标注的，一并重算）
    rows = await conn.fetch(
        """
        SELECT id, start_lat, start_lng, end_lat, end_lng
        FROM track_segment
        WHERE started_at >= $1
          AND ended_at IS NOT NULL
          AND start_lat IS NOT NULL AND start_lng IS NOT NULL
          AND end_lat   IS NOT NULL AND end_lng   IS NOT NULL
        """,
        cutoff,
    )

    labeled = 0
    for row in rows:
        start_zone = _zone_type(float(row["start_lat"]), float(row["start_lng"]))
        end_zone   = _zone_type(float(row["end_lat"]),   float(row["end_lng"]))

        if start_zone == "loading" and end_zone == "unloading":
            seg_type: Optional[str] = "loading"
        elif start_zone == "unloading" and end_zone == "loading":
            seg_type = "unloading"
        else:
            seg_type = None  # 清除可能存在的旧错误标注

        await conn.execute(
            "UPDATE track_segment SET segment_type = $1 WHERE id = $2",
            seg_type, int(row["id"]),
        )
        if seg_type:
            labeled += 1

    return ok({"labeled": labeled, "total_checked": len(rows)})


@router.post("/resegment-history")
async def resegment_history(
    days: int = 7,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """
    全量历史轨迹重分割：从原始定位点重建轨迹段。

    分割规则（仅一条）：
      相邻两点时间间隔 > park_threshold_min → 切断。
      【不】按围栏边界切段——保留完整的取土区→弃土区运输段。

    标注规则（起终点围栏对）：
      - 起点在取土区 + 终点在弃土区 → loading（装料运输段）
      - 起点在弃土区 + 终点在取土区 → unloading（空载返回段）
      - 其他（同侧 / 均不在围栏 / 仅一端在围栏）→ NULL，不标注

    操作：删除范围内旧 track_segment，重建并更新 location_point.segment_id。
    """
    from app.core.enums import ZoneType
    from app.services.geofence_service import _load_zones, point_in_polygon, wgs84_to_gcj02

    cfg = await _business_config_repo.get_singleton(conn)
    park_threshold_s: float = (cfg.park_threshold_min if cfg else 10) * 60

    zones = await _load_zones(conn)
    loading_zones  = [z for z in zones if z.zone_type == ZoneType.LOADING]
    unloading_zones = [z for z in zones if z.zone_type == ZoneType.UNLOADING]

    def _zone_type(lat_wgs: float, lng_wgs: float) -> Optional[str]:
        lat_g, lng_g = wgs84_to_gcj02(lat_wgs, lng_wgs)
        for z in loading_zones:
            if z.coordinates and point_in_polygon(lat_g, lng_g, z.coordinates):
                return "loading"
        for z in unloading_zones:
            if z.coordinates and point_in_polygon(lat_g, lng_g, z.coordinates):
                return "unloading"
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    device_rows = await conn.fetch(
        "SELECT DISTINCT device_id FROM location_point WHERE recorded_at >= $1",
        cutoff,
    )

    total_created = 0
    total_devices = len(device_rows)

    for dev_row in device_rows:
        device_id = int(dev_row["device_id"])

        # 删除旧段并解除 location_point 关联
        old_seg_ids = [
            int(r["id"])
            for r in await conn.fetch(
                "SELECT id FROM track_segment WHERE device_id = $1 AND started_at >= $2",
                device_id, cutoff,
            )
        ]
        if old_seg_ids:
            await conn.execute(
                "UPDATE location_point SET segment_id = NULL"
                " WHERE segment_id = ANY($1::BIGINT[]) AND recorded_at >= $2",
                old_seg_ids, cutoff,
            )
            await conn.execute(
                "DELETE FROM track_segment WHERE id = ANY($1::BIGINT[])",
                old_seg_ids,
            )

        pts = await conn.fetch(
            """
            SELECT id, vehicle_id, recorded_at,
                   lat::DOUBLE PRECISION AS lat,
                   lng::DOUBLE PRECISION AS lng
            FROM location_point
            WHERE device_id = $1 AND recorded_at >= $2
            ORDER BY recorded_at ASC, id ASC
            """,
            device_id, cutoff,
        )
        if not pts:
            continue

        # ── 按时间间隔切段（不按围栏边界切）────────────────────────
        raw_segments: list[list] = []
        cur: list = [pts[0]]
        for i in range(1, len(pts)):
            gap_s = (pts[i]["recorded_at"] - pts[i - 1]["recorded_at"]).total_seconds()
            if gap_s > park_threshold_s:
                raw_segments.append(cur)
                cur = [pts[i]]
            else:
                cur.append(pts[i])
        raw_segments.append(cur)

        # ── 插入新段，按起终点围栏对确定 segment_type ───────────────
        for seg_pts in raw_segments:
            if not seg_pts:
                continue

            started_at = seg_pts[0]["recorded_at"]
            ended_at   = seg_pts[-1]["recorded_at"]
            start_lat  = float(seg_pts[0]["lat"])
            start_lng  = float(seg_pts[0]["lng"])
            end_lat    = float(seg_pts[-1]["lat"])
            end_lng    = float(seg_pts[-1]["lng"])

            vehicle_id: Optional[int] = None
            for p in reversed(seg_pts):
                if p["vehicle_id"] is not None:
                    vehicle_id = int(p["vehicle_id"])
                    break

            # 起终点围栏对判定
            s_zone = _zone_type(start_lat, start_lng)
            e_zone = _zone_type(end_lat,   end_lng)

            if s_zone == "loading" and e_zone == "unloading":
                seg_type: Optional[str] = "loading"    # 取土→弃土：装料运输
            elif s_zone == "unloading" and e_zone == "loading":
                seg_type = "unloading"                  # 弃土→取土：空载返回
            else:
                seg_type = None                         # 单侧/同侧/路途中：不标注

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

            pt_ids = [int(p["id"]) for p in seg_pts]
            await conn.execute(
                "UPDATE location_point SET segment_id = $1"
                " WHERE id = ANY($2::BIGINT[]) AND recorded_at >= $3",
                seg_id, pt_ids, cutoff,
            )
            total_created += 1

    return ok({"segments_created": total_created, "devices_processed": total_devices})
