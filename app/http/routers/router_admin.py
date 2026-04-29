from __future__ import annotations

from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.cache.session_repo import SessionData
from app.core.exceptions import NotFoundError, ValidationError
from app.db.deps import get_db_conn
from app.db.repos.fleet_repo import FleetRepo
from app.http.deps import require_manager
from app.http.response import ok

router = APIRouter(prefix="/api/admin", tags=["admin"])
_fleet_repo = FleetRepo()


class FleetCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    notes: Optional[str] = None


class FleetResponse(BaseModel):
    id: int
    name: str
    notes: Optional[str]


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
