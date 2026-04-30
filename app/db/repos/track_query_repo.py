from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

_SEGMENT_LIST_SQL = """
    SELECT
        ts.id,
        ts.device_id,
        ts.vehicle_id,
        v.license_plate,
        ts.started_at,
        ts.ended_at,
        ts.start_lat,
        ts.start_lng,
        ts.end_lat,
        ts.end_lng,
        ts.point_count,
        lp_end.lat AS last_lat,
        lp_end.lng AS last_lng,
        COALESCE(lp_start.loc_type::text, 'gps') AS start_loc_type,
        COALESCE(lp_end.loc_type::text, 'gps') AS end_loc_type
    FROM track_segment ts
    LEFT JOIN vehicle v
        ON v.id = ts.vehicle_id AND v.deleted_at IS NULL
    LEFT JOIN LATERAL (
        SELECT loc_type
        FROM location_point
        WHERE segment_id = ts.id
        ORDER BY recorded_at ASC, id ASC
        LIMIT 1
    ) lp_start ON TRUE
    LEFT JOIN LATERAL (
        SELECT lat, lng, loc_type
        FROM location_point
        WHERE segment_id = ts.id
        ORDER BY recorded_at DESC, id DESC
        LIMIT 1
    ) lp_end ON TRUE
    WHERE ts.started_at >= $1
      AND ts.started_at < $2
      AND ($3::BIGINT IS NULL OR ts.vehicle_id = $3)
      AND (
          $4::BIGINT IS NULL
          OR v.fleet_id = $4
      )
    ORDER BY ts.started_at DESC
    LIMIT $5
"""

_DISTANCE_KM_SQL = """
    WITH ordered AS (
        SELECT
            segment_id,
            lat::DOUBLE PRECISION AS lat,
            lng::DOUBLE PRECISION AS lng,
            LAG(lat::DOUBLE PRECISION) OVER (
                PARTITION BY segment_id ORDER BY recorded_at, id
            ) AS prev_lat,
            LAG(lng::DOUBLE PRECISION) OVER (
                PARTITION BY segment_id ORDER BY recorded_at, id
            ) AS prev_lng
        FROM location_point
        WHERE segment_id = ANY($1::BIGINT[])
    )
    SELECT
        segment_id,
        COALESCE(
            SUM(
                CASE
                    WHEN prev_lat IS NULL THEN 0.0
                    ELSE 6371.0088 * ACOS(
                        LEAST(
                            1.0,
                            GREATEST(
                                -1.0,
                                SIN(RADIANS(prev_lat)) * SIN(RADIANS(lat))
                                + COS(RADIANS(prev_lat)) * COS(RADIANS(lat))
                                * COS(RADIANS(lng - prev_lng))
                            )
                        )
                    )
                END
            ),
            0.0
        ) AS distance_km
    FROM ordered
    GROUP BY segment_id
"""

_POINTS_SQL = """
    SELECT
        recorded_at,
        lat::DOUBLE PRECISION,
        lng::DOUBLE PRECISION,
        speed::DOUBLE PRECISION,
        COALESCE(loc_type::TEXT, 'gps') AS loc_type
    FROM location_point
    WHERE segment_id = $1
    ORDER BY recorded_at ASC, id ASC
    LIMIT $2
"""


@dataclass(frozen=True)
class TrackSegmentListRow:
    id: int
    device_id: int
    vehicle_id: Optional[int]
    license_plate: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    start_lat: Optional[float]
    start_lng: Optional[float]
    end_lat: Optional[float]
    end_lng: Optional[float]
    point_count: int
    last_lat: Optional[float]
    last_lng: Optional[float]
    start_loc_type: str
    end_loc_type: str


@dataclass(frozen=True)
class TrackPointRow:
    recorded_at: datetime
    lat: float
    lng: float
    speed: Optional[float]
    loc_type: str


class TrackQueryRepo:
    async def list_segments(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        *,
        started_from: datetime,
        started_to: datetime,
        vehicle_id: Optional[int],
        fleet_id: Optional[int],
        limit: int = 200,
    ) -> list[TrackSegmentListRow]:
        rows = await conn.fetch(
            _SEGMENT_LIST_SQL,
            started_from,
            started_to,
            vehicle_id,
            fleet_id,
            limit,
        )
        out: list[TrackSegmentListRow] = []
        for r in rows:
            out.append(
                TrackSegmentListRow(
                    id=int(r["id"]),
                    device_id=int(r["device_id"]),
                    vehicle_id=int(r["vehicle_id"]) if r["vehicle_id"] is not None else None,
                    license_plate=r["license_plate"],
                    started_at=r["started_at"],
                    ended_at=r["ended_at"],
                    start_lat=float(r["start_lat"]) if r["start_lat"] is not None else None,
                    start_lng=float(r["start_lng"]) if r["start_lng"] is not None else None,
                    end_lat=float(r["end_lat"]) if r["end_lat"] is not None else None,
                    end_lng=float(r["end_lng"]) if r["end_lng"] is not None else None,
                    point_count=int(r["point_count"]),
                    last_lat=float(r["last_lat"]) if r["last_lat"] is not None else None,
                    last_lng=float(r["last_lng"]) if r["last_lng"] is not None else None,
                    start_loc_type=str(r["start_loc_type"] or "gps"),
                    end_loc_type=str(r["end_loc_type"] or "gps"),
                )
            )
        return out

    async def distance_km_for_segments(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        segment_ids: list[int],
    ) -> dict[int, float]:
        if not segment_ids:
            return {}
        rows = await conn.fetch(_DISTANCE_KM_SQL, segment_ids)
        return {int(r["segment_id"]): float(r["distance_km"]) for r in rows}

    async def list_points(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        segment_id: int,
        max_points: int = 25000,
    ) -> list[TrackPointRow]:
        rows = await conn.fetch(_POINTS_SQL, segment_id, max_points)
        return [
            TrackPointRow(
                recorded_at=r["recorded_at"],
                lat=float(r["lat"]),
                lng=float(r["lng"]),
                speed=float(r["speed"]) if r["speed"] is not None else None,
                loc_type=str(r["loc_type"]),
            )
            for r in rows
        ]

    async def delete_segment(self, conn: asyncpg.Connection, segment_id: int) -> bool:  # type: ignore[type-arg]
        """删除轨迹段及其下属定位点（管理员）。"""
        async with conn.transaction():
            await conn.execute("DELETE FROM location_point WHERE segment_id = $1", segment_id)
            status = await conn.execute("DELETE FROM track_segment WHERE id = $1", segment_id)
        parts = status.split()
        return len(parts) >= 2 and parts[0] == "DELETE" and int(parts[1]) > 0
