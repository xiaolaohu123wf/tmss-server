from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from app.cache.session_repo import SessionData
from app.db.deps import get_db_conn
from app.http.deps import require_fleet_or_above, require_manager
from app.http.response import ok
from app.models.http_geo_zone import GeoZoneCreate, GeoZoneUpdate
from app.services.geo_zone_service import GeoZoneService

router = APIRouter(prefix="/api/geo-zones", tags=["geo_zones"])
_svc = GeoZoneService()


@router.get("")
async def list_zones(
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    data = await _svc.list_zones(conn)
    return ok([z.model_dump() for z in data])


@router.get("/{zone_id}")
async def get_zone(
    zone_id: int,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    data = await _svc.get_zone(conn, zone_id)
    return ok(data.model_dump())


@router.post("")
async def create_zone(
    body: GeoZoneCreate,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    data = await _svc.create_zone(conn, body)
    return ok(data.model_dump())


@router.put("/{zone_id}")
async def update_zone(
    zone_id: int,
    body: GeoZoneUpdate,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    data = await _svc.update_zone(conn, zone_id, body)
    return ok(data.model_dump())


@router.delete("/{zone_id}")
async def delete_zone(
    zone_id: int,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    await _svc.delete_zone(conn, zone_id)
    return ok({"message": "已删除"})
