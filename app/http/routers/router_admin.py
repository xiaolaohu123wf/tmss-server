from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import structlog
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
logger = structlog.get_logger()
_fleet_repo = FleetRepo()
_user_repo = UserRepo()
_business_config_repo = BusinessConfigRepo()


class BusinessConfigPayload(BaseModel):
    """与前端 Settings 表单一致（v1.2.2 起移除 dwell 字段）。"""

    global_speed_limit: int = Field(ge=10, le=200)
    park_threshold_min: int = Field(ge=1, le=60)
    alert_cooldown_s: int = Field(ge=1, le=300)
    hb_timeout_s: int = Field(ge=30, le=600)
    weather_city: str = Field(min_length=1, max_length=50)
    map_center_lng: float = Field(ge=-180, le=180)
    map_center_lat: float = Field(ge=-90, le=90)
    map_zoom: int = Field(default=15, ge=3, le=20)
    transport_timeout_min: int = Field(ge=0, le=480)
    segment_buffer_min: int = Field(default=3, ge=0, le=30)

    def to_repo_kwargs(self) -> dict[str, int | str | float]:
        return {
            "global_speed_limit": self.global_speed_limit,
            "park_threshold_min": self.park_threshold_min,
            "alert_cooldown_s": self.alert_cooldown_s,
            "hb_timeout_s": self.hb_timeout_s,
            "weather_city": self.weather_city,
            "map_center_lng": self.map_center_lng,
            "map_center_lat": self.map_center_lat,
            "map_zoom": self.map_zoom,
            "transport_timeout_min": self.transport_timeout_min,
            "segment_buffer_min": self.segment_buffer_min,
        }


class MapCenterPayload(BaseModel):
    """地图默认中心点和缩放，供所有已登录用户读取。"""

    map_center_lng: float
    map_center_lat: float
    map_zoom: int = 15


def _payload_from_row(row: BusinessConfigRow) -> BusinessConfigPayload:
    return BusinessConfigPayload(
        global_speed_limit=row.global_speed_limit,
        park_threshold_min=row.park_threshold_min,
        alert_cooldown_s=row.alert_cooldown_s,
        hb_timeout_s=row.hb_timeout_s,
        weather_city=row.weather_city,
        map_center_lng=row.map_center_lng,
        map_center_lat=row.map_center_lat,
        map_zoom=row.map_zoom,
        transport_timeout_min=row.transport_timeout_min,
        segment_buffer_min=row.segment_buffer_min,
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
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """返回当前城市天气，优先缓存；缓存缺失时主动拉取一次。"""
    from app.cache.pool import get_redis
    from app.cache.weather_cache import WeatherCache
    from app.services.weather_service import WeatherService

    cfg = await _business_config_repo.get_singleton(conn)
    city = (cfg.weather_city if cfg else "Nanjing").strip() or "Nanjing"

    cache = WeatherCache()
    cached = await cache.get(get_redis(), city)
    if not cached:
        # 兜底拉取，避免前端在设备尚未请求 rw 时一直拿不到当前城市天气。
        reply = await WeatherService().get_weather_reply(city)
        cached = reply[1:] if reply.startswith("w") else None
    if not cached:
        cached = await cache.get_legacy(get_redis())
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
        return ok({"map_center_lng": 109.2695, "map_center_lat": 30.383164, "map_zoom": 15})
    return ok(MapCenterPayload(
        map_center_lng=row.map_center_lng,
        map_center_lat=row.map_center_lat,
        map_zoom=row.map_zoom,
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
    起点在装/卸料围栏内即直接打标，无驻留时长限制（v1.2.2 起）。
    """
    from app.core.enums import ZoneType
    from app.services.geofence_service import _load_zones, invalidate_zone_cache, point_in_polygon, wgs84_to_gcj02

    # 强制刷新围栏缓存，确保使用最新的围栏坐标
    invalidate_zone_cache()

    zones = await _load_zones(conn)
    loading_zones = [z for z in zones if z.zone_type == ZoneType.LOADING]
    unloading_zones = [z for z in zones if z.zone_type == ZoneType.UNLOADING]

    if not loading_zones and not unloading_zones:
        return ok({"labeled": 0, "total_checked": 0, "message": "未发现已启用的取土/弃土围栏"})

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await conn.fetch(
        """
        SELECT id, start_lat, start_lng
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
        lat_gcj, lng_gcj = wgs84_to_gcj02(float(row["start_lat"]), float(row["start_lng"]))
        seg_type: Optional[str] = None

        for z in loading_zones:
            if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
                seg_type = "loading"
                break
        if seg_type is None:
            for z in unloading_zones:
                if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
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
    历史轨迹全量重分析（v1.2.0）。

    使用六态状态机（SegmentFSM）从原始 GPS 定位点重建所有轨迹段，
    支持：装料/卸料驻留确认、重载/空载运输、运输超时→unknown、
    停车→idle（可隐藏）等精确分段逻辑。

    操作：删除 cutoff 之后的旧 track_segment，重新创建新段。
    location_point 数据不受影响（v1.2.0 已去除 segment_id 字段）。
    """
    from app.core.enums import ZoneType
    from app.services.geofence_service import _load_zones, invalidate_zone_cache
    from app.services.segment_resegment_service import resegment_device

    # 强制刷新围栏缓存，确保使用最新的围栏坐标
    invalidate_zone_cache()

    cfg = await _business_config_repo.get_singleton(conn)
    park_threshold_min: int = cfg.park_threshold_min if cfg else 10
    transport_timeout_min: int = cfg.transport_timeout_min if cfg else 30

    all_zones = await _load_zones(conn)
    loading_zones   = [z for z in all_zones if z.zone_type == ZoneType.LOADING]
    unloading_zones = [z for z in all_zones if z.zone_type == ZoneType.UNLOADING]

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    device_rows = await conn.fetch(
        "SELECT DISTINCT device_id FROM location_point WHERE recorded_at >= $1 AND loc_type = 'gps'",
        cutoff,
    )

    total_created = 0
    total_devices = len(device_rows)
    errors: list[str] = []

    for dev_row in device_rows:
        device_id = int(dev_row["device_id"])
        try:
            created = await resegment_device(
                device_id=device_id,
                cutoff=cutoff,
                conn=conn,
                park_threshold_min=park_threshold_min,
                transport_timeout_min=transport_timeout_min,
                loading_zones=loading_zones,
                unloading_zones=unloading_zones,
            )
            total_created += created
        except Exception as exc:
            await logger.awarning(
                "resegment_device_error",
                device_id=device_id,
                error=str(exc),
            )
            errors.append(f"device {device_id}: {exc}")

    return ok({
        "segments_created": total_created,
        "devices_processed": total_devices,
        "errors": errors,
    })
