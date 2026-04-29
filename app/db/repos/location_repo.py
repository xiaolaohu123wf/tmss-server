from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

from app.db.queries.location import INSERT_LOCATION_BATCH_COLUMNS


@dataclass(frozen=True)
class LocationRow:
    device_id: int
    vehicle_id: Optional[int]
    segment_id: Optional[int]
    recorded_at: datetime
    lat: float
    lng: float
    speed: Optional[float]
    altitude: Optional[float]
    loc_type: str = "gps"


class LocationRepo:
    async def insert_batch(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        points: list[LocationRow],
    ) -> None:
        if not points:
            return
        records = [
            (
                p.device_id, p.vehicle_id, p.segment_id,
                p.recorded_at, p.lat, p.lng, p.speed, p.altitude, p.loc_type,
            )
            for p in points
        ]
        await conn.copy_records_to_table(
            "location_point",
            records=records,
            columns=INSERT_LOCATION_BATCH_COLUMNS,
        )
