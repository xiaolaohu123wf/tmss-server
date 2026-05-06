from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

from app.db.queries.track_segment import (
    CLOSE_SEGMENT_SQL,
    INCREMENT_SEGMENT_POINTS_SQL,
    INSERT_SEGMENT_SQL,
    SELECT_OPEN_SEGMENT_BY_DEVICE_SQL,
)


@dataclass(frozen=True)
class TrackSegmentRow:
    id: int
    device_id: int
    vehicle_id: Optional[int]
    started_at: datetime
    start_lat: Optional[float]
    start_lng: Optional[float]
    point_count: int
    segment_type: Optional[str] = None


class TrackSegmentRepo:
    async def open_segment(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        device_id: int,
        started_at: datetime,
        start_lat: float,
        start_lng: float,
        vehicle_id: Optional[int] = None,
        segment_type: Optional[str] = None,
    ) -> int:
        segment_id: int = await conn.fetchval(
            INSERT_SEGMENT_SQL,
            device_id, vehicle_id, started_at, start_lat, start_lng, segment_type,
        )
        return segment_id

    async def close_segment(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        segment_id: int,
        ended_at: datetime,
        end_lat: float,
        end_lng: float,
        extra_points: int = 0,
    ) -> None:
        await conn.execute(
            CLOSE_SEGMENT_SQL,
            segment_id, ended_at, end_lat, end_lng, extra_points,
        )

    async def increment_points(
        self, conn: asyncpg.Connection, segment_id: int  # type: ignore[type-arg]
    ) -> None:
        await conn.execute(INCREMENT_SEGMENT_POINTS_SQL, segment_id)

    async def find_open_by_device(
        self, conn: asyncpg.Connection, device_id: int  # type: ignore[type-arg]
    ) -> Optional[TrackSegmentRow]:
        row = await conn.fetchrow(SELECT_OPEN_SEGMENT_BY_DEVICE_SQL, device_id)
        if not row:
            return None
        return TrackSegmentRow(
            id=row["id"],
            device_id=row["device_id"],
            vehicle_id=row["vehicle_id"],
            started_at=row["started_at"],
            start_lat=float(row["start_lat"]) if row["start_lat"] is not None else None,
            start_lng=float(row["start_lng"]) if row["start_lng"] is not None else None,
            point_count=row["point_count"],
            segment_type=row["segment_type"],
        )
