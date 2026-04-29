from __future__ import annotations

from datetime import datetime
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.cache.session_repo import SessionData
from app.db.deps import get_db_conn
from app.db.repos.event_repo import EventRepo
from app.http.deps import require_fleet_or_above
from app.http.response import ok
from app.models.http_event import EventListResponse, EventResponse

router = APIRouter(prefix="/api/events", tags=["events"])
_repo = EventRepo()


@router.get("")
async def list_events(
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
    vehicle_id: Optional[int] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> dict:
    total, rows = await _repo.find_page(
        conn,
        fleet_id=session.fleet_id,
        vehicle_id=vehicle_id,
        event_type=event_type,
        start=start,
        end=end,
        page=page,
        size=size,
    )
    items = [
        EventResponse(
            id=r.id,
            device_id=r.device_id,
            vehicle_id=r.vehicle_id,
            event_type=r.event_type,
            severity=r.severity,
            zone_id=r.zone_id,
            lat=r.lat,
            lng=r.lng,
            speed=r.speed,
            cmd_sent=r.cmd_sent,
            detail=r.detail,
            occurred_at=r.occurred_at,
        ).model_dump()
        for r in rows
    ]
    return ok({"total": total, "items": items})
