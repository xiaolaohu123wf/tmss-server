from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends

from app.cache.session_repo import SessionData
from app.db.deps import get_db_conn
from app.http.deps import require_auth, require_fleet_or_above
from app.http.response import ok
from app.models.http_vehicle import VehicleCreate, VehicleUpdate
from app.services.vehicle_service import VehicleService

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])
_svc = VehicleService()


@router.get("")
async def list_vehicles(
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    data = await _svc.list_vehicles(conn, session)
    return ok([v.model_dump() for v in data])


@router.get("/{vehicle_id}")
async def get_vehicle(
    vehicle_id: int,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    data = await _svc.get_vehicle(conn, vehicle_id, session)
    return ok(data.model_dump())


@router.post("")
async def create_vehicle(
    body: VehicleCreate,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    data = await _svc.create_vehicle(conn, body, session)
    return ok(data.model_dump())


@router.put("/{vehicle_id}")
async def update_vehicle(
    vehicle_id: int,
    body: VehicleUpdate,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    data = await _svc.update_vehicle(conn, vehicle_id, body, session)
    return ok(data.model_dump())


@router.delete("/{vehicle_id}")
async def delete_vehicle(
    vehicle_id: int,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    await _svc.delete_vehicle(conn, vehicle_id, session)
    return ok({"message": "已删除"})
