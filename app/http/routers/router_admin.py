from __future__ import annotations

from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.cache.session_repo import SessionData
from app.core.exceptions import NotFoundError, ValidationError
from app.db.deps import get_db_conn
from app.db.repos.business_config_repo import BusinessConfigRepo, BusinessConfigRow
from app.db.repos.fleet_repo import FleetRepo
from app.http.deps import require_manager, require_password_confirm
from app.http.response import ok
from app.tcp.connection import invalidate_gps_handler

router = APIRouter(prefix="/api/admin", tags=["admin"])
_fleet_repo = FleetRepo()
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


class FleetResponse(BaseModel):
    id: int
    name: str
    notes: Optional[str]


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
    new_id = await _fleet_repo.create(
        conn, name=body.name, notes=body.notes,
    )
    row = await _fleet_repo.find_by_id(conn, new_id)
    assert row is not None
    return ok(FleetResponse(id=row.id, name=row.name, notes=row.notes).model_dump())


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
