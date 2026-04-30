from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.cache.session_repo import SessionData
from app.core.enums import UserRole
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.db.deps import get_db_conn
from app.db.repos.track_query_repo import TrackQueryRepo
from app.http.deps import require_fleet_or_above
from app.http.response import ok
from app.services.geofence_service import get_zones_at

router = APIRouter(prefix="/api/track-segments", tags=["track-segments"])
_repo = TrackQueryRepo()


def _fleet_filter(session: SessionData) -> Optional[int]:
    return None if session.role == UserRole.MANAGER else session.fleet_id


async def _zone_label(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    lat: Optional[float],
    lng: Optional[float],
) -> Optional[str]:
    if lat is None or lng is None:
        return None
    zones = await get_zones_at(lat, lng, conn)
    if not zones:
        return None
    return zones[0].name


async def _ensure_segment_access(
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    segment_id: int,
    session: SessionData,
) -> None:
    row = await conn.fetchrow(
        """
        SELECT ts.vehicle_id, v.fleet_id
        FROM track_segment ts
        LEFT JOIN vehicle v ON v.id = ts.vehicle_id AND v.deleted_at IS NULL
        WHERE ts.id = $1
        """,
        segment_id,
    )
    if row is None:
        raise NotFoundError("轨迹段不存在")
    if row["vehicle_id"] is None:
        if session.role != UserRole.MANAGER:
            raise PermissionDeniedError("无权访问该轨迹")
        return
    fleet_id = row["fleet_id"]
    if session.role == UserRole.FLEET_CAPTAIN and fleet_id != session.fleet_id:
        raise PermissionDeniedError("无权访问其他车队数据")


class TrackSegmentListItem(BaseModel):
    id: int
    vehicle_id: Optional[int]
    license_plate: Optional[str]
    started_at: str
    ended_at: Optional[str]
    distance_km: float
    start_zone_name: Optional[str]
    end_zone_name: Optional[str]
    cargo_name: Optional[str] = None
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    end_lat: Optional[float] = None
    end_lng: Optional[float] = None


class TrackPointItem(BaseModel):
    recorded_at: str
    lat: float
    lng: float
    speed: Optional[float]
    loc_type: str


@router.get("")
async def list_track_segments(
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
    from_: datetime = Query(..., alias="from"),
    to: datetime = Query(..., alias="to"),
    vehicle_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    if to <= from_:
        return ok([])

    if from_.tzinfo is None:
        from_ = from_.replace(tzinfo=timezone.utc)
    if to.tzinfo is None:
        to = to.replace(tzinfo=timezone.utc)

    ff = _fleet_filter(session)
    rows = await _repo.list_segments(
        conn,
        started_from=from_,
        started_to=to,
        vehicle_id=vehicle_id,
        fleet_id=ff,
        limit=limit,
    )
    ids = [r.id for r in rows]
    dist_map = await _repo.distance_km_for_segments(conn, ids)

    items: list[dict] = []
    for r in rows:
        s_lat, s_lng = r.start_lat, r.start_lng
        e_lat = r.end_lat if r.end_lat is not None else r.last_lat
        e_lng = r.end_lng if r.end_lng is not None else r.last_lng

        start_zone = await _zone_label(conn, s_lat, s_lng)
        end_zone = await _zone_label(conn, e_lat, e_lng)

        item = TrackSegmentListItem(
            id=r.id,
            vehicle_id=r.vehicle_id,
            license_plate=r.license_plate,
            started_at=r.started_at.isoformat(),
            ended_at=r.ended_at.isoformat() if r.ended_at else None,
            distance_km=round(dist_map.get(r.id, 0.0), 3),
            start_zone_name=start_zone,
            end_zone_name=end_zone,
            cargo_name=None,
            start_lat=s_lat,
            start_lng=s_lng,
            end_lat=e_lat,
            end_lng=e_lng,
        )
        items.append(item.model_dump())

    return ok(items)


@router.get("/{segment_id}/points")
async def get_segment_points(
    segment_id: int,
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
    limit: int = Query(25000, ge=100, le=50000),
) -> dict:
    await _ensure_segment_access(conn, segment_id, session)
    pts = await _repo.list_points(conn, segment_id, max_points=limit)
    data = [
        TrackPointItem(
            recorded_at=p.recorded_at.isoformat(),
            lat=p.lat,
            lng=p.lng,
            speed=p.speed,
            loc_type=p.loc_type,
        ).model_dump()
        for p in pts
    ]
    return ok(data)
