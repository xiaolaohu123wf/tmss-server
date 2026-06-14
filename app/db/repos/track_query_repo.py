from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

# 段列表查询。
# 优化要点：
#   1. 去掉了两个 LATERAL 子查询（原用于获取 start/end loc_type），
#      改为直接从 track_segment 读取起终坐标，loc_type 固定为 'gps'（见路由层注释）。
#      单次查询从 O(N×location_point 扫描) 降至 O(1) 纯索引扫描。
#   2. 直接 SELECT distance_km 存储列；NULL 仅出现在开放段或 V011 前的历史段，
#      路由层对空值集合再调 _DISTANCE_KM_SQL 降级计算。
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
        ts.segment_type,
        ts.distance_km
    FROM track_segment ts
    LEFT JOIN vehicle v
        ON v.id = ts.vehicle_id AND v.deleted_at IS NULL
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

# 里程计算：通过 device_id + 时间范围关联定位点
_DISTANCE_KM_SQL = """
    WITH segs AS (
        SELECT id AS segment_id, device_id,
               started_at,
               COALESCE(ended_at, NOW()) AS ended_at
        FROM track_segment
        WHERE id = ANY($1::BIGINT[])
    ),
    ordered AS (
        SELECT
            s.segment_id,
            lp.lat::DOUBLE PRECISION  AS lat,
            lp.lng::DOUBLE PRECISION  AS lng,
            LAG(lp.lat::DOUBLE PRECISION) OVER (
                PARTITION BY s.segment_id ORDER BY lp.recorded_at, lp.id
            ) AS prev_lat,
            LAG(lp.lng::DOUBLE PRECISION) OVER (
                PARTITION BY s.segment_id ORDER BY lp.recorded_at, lp.id
            ) AS prev_lng
        FROM segs s
        JOIN location_point lp
            ON  lp.device_id   = s.device_id
            AND lp.recorded_at >= s.started_at
            AND lp.recorded_at <= s.ended_at
            AND lp.loc_type = 'gps'
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

# 定位点查询：通过 device_id + 时间范围（含可选缓冲）获取
# $1 = segment_id, $2 = max_points, $3 = buffer_min（运输段用 3，其余用 0）
_POINTS_SQL = """
    SELECT
        lp.recorded_at,
        lp.lat::DOUBLE PRECISION,
        lp.lng::DOUBLE PRECISION,
        lp.speed::DOUBLE PRECISION,
        COALESCE(lp.loc_type::TEXT, 'gps') AS loc_type
    FROM track_segment ts
    JOIN location_point lp
        ON  lp.device_id   = ts.device_id
        AND lp.recorded_at >= (ts.started_at    - ($3 * INTERVAL '1 minute'))
        AND lp.recorded_at <= (COALESCE(ts.ended_at, NOW()) + ($3 * INTERVAL '1 minute'))
        AND lp.loc_type = 'gps'
    WHERE ts.id = $1
    ORDER BY lp.recorded_at ASC, lp.id ASC
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
    segment_type: Optional[str]
    # V011+: 关闭时预计算写入，NULL 表示开放段或历史未填充段，路由层降级处理
    distance_km: Optional[float]


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
                    segment_type=r["segment_type"],
                    distance_km=float(r["distance_km"]) if r["distance_km"] is not None else None,
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
        buffer_min: int = 0,
    ) -> list[TrackPointRow]:
        rows = await conn.fetch(_POINTS_SQL, segment_id, max_points, buffer_min)
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

    async def delete_segment(
        self, conn: asyncpg.Connection, segment_id: int  # type: ignore[type-arg]
    ) -> bool:
        """删除轨迹段（location_point 按时间范围关联，删除段记录即可）。"""
        status = await conn.execute("DELETE FROM track_segment WHERE id = $1", segment_id)
        parts = status.split()
        return len(parts) >= 2 and parts[0] == "DELETE" and int(parts[1]) > 0
