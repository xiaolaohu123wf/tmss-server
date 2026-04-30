from __future__ import annotations

from datetime import datetime, timezone
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

    def to_repo_kwargs(self) -> dict[str, int | str]:
        return {
            "global_speed_limit": self.global_speed_limit,
            "park_threshold_min": self.park_threshold_min,
            "loading_dwell_min": self.loading_min_stay_s,
            "unloading_dwell_min": self.unloading_min_stay_s,
            "alert_cooldown_s": self.alert_cooldown_s,
            "hb_timeout_s": self.hb_timeout_s,
            "weather_city": self.weather_city,
        }


def _payload_from_row(row: BusinessConfigRow) -> BusinessConfigPayload:
    return BusinessConfigPayload(
        global_speed_limit=row.global_speed_limit,
        park_threshold_min=row.park_threshold_min,
        alert_cooldown_s=row.alert_cooldown_s,
        hb_timeout_s=row.hb_timeout_s,
        loading_min_stay_s=row.loading_dwell_min,
        unloading_min_stay_s=row.unloading_dwell_min,
        weather_city=row.weather_city,
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
