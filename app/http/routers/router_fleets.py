from __future__ import annotations

from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.cache.session_repo import SessionData
from app.core.exceptions import NotFoundError
from app.db.deps import get_db_conn
from app.db.repos.fleet_repo import FleetRepo
from app.http.deps import require_fleet_captain, require_fleet_or_above
from app.http.response import ok

router = APIRouter(prefix="/api/fleets", tags=["fleets"])
_fleet_repo = FleetRepo()


class FleetMeResponse(BaseModel):
    id: int
    name: str
    notes: Optional[str]


class FleetMeUpdateRequest(BaseModel):
    notes: Optional[str] = None


@router.get("/me")
async def get_my_fleet(
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """返回当前登录用户所属车队信息。manager 角色无车队，返回 null。"""
    if session.fleet_id is None:
        return ok(None)
    row = await _fleet_repo.find_by_id(conn, session.fleet_id)
    if row is None:
        return ok(None)
    return ok(FleetMeResponse(id=row.id, name=row.name, notes=row.notes).model_dump())


@router.patch("/me")
async def update_my_fleet_notes(
    body: FleetMeUpdateRequest,
    session: SessionData = Depends(require_fleet_captain),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """车队长编辑本队备注（仅备注，名称由管理员维护）。"""
    if session.fleet_id is None:
        raise NotFoundError("当前用户未关联任何车队")
    row = await _fleet_repo.find_by_id(conn, session.fleet_id)
    if row is None:
        raise NotFoundError("车队不存在")
    await _fleet_repo.update_notes(conn, session.fleet_id, body.notes)
    updated = await _fleet_repo.find_by_id(conn, session.fleet_id)
    assert updated is not None
    return ok(FleetMeResponse(id=updated.id, name=updated.name, notes=updated.notes).model_dump())
