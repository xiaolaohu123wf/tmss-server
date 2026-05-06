from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg

from app.db.queries.business_config import SELECT_BUSINESS_CONFIG_SQL

UPDATE_BUSINESS_CONFIG_SQL = """
    UPDATE business_config SET
        global_speed_limit  = $1,
        park_threshold_min  = $2,
        alert_cooldown_s    = $3,
        hb_timeout_s        = $4,
        weather_city        = $5,
        map_center_lng      = $6,
        map_center_lat      = $7,
        transport_timeout_min = $8,
        segment_buffer_min  = $9
    WHERE id = 1
"""


@dataclass(frozen=True)
class BusinessConfigRow:
    global_speed_limit: int
    park_threshold_min: int
    alert_cooldown_s: int
    hb_timeout_s: int
    weather_city: str
    map_center_lng: float
    map_center_lat: float
    transport_timeout_min: int
    segment_buffer_min: int = 3


def _row_from_record(r: asyncpg.Record) -> BusinessConfigRow:  # type: ignore[name-defined]
    return BusinessConfigRow(
        global_speed_limit=int(r["global_speed_limit"]),
        park_threshold_min=int(r["park_threshold_min"]),
        alert_cooldown_s=int(r["alert_cooldown_s"]),
        hb_timeout_s=int(r["hb_timeout_s"]),
        weather_city=str(r["weather_city"]),
        map_center_lng=float(r["map_center_lng"]),
        map_center_lat=float(r["map_center_lat"]),
        transport_timeout_min=int(r["transport_timeout_min"]),
        segment_buffer_min=int(r["segment_buffer_min"]) if r["segment_buffer_min"] is not None else 3,
    )


class BusinessConfigRepo:
    async def get_singleton(
        self, conn: asyncpg.Connection  # type: ignore[type-arg]
    ) -> Optional[BusinessConfigRow]:
        r = await conn.fetchrow(SELECT_BUSINESS_CONFIG_SQL)
        if r is None:
            return None
        return _row_from_record(r)

    async def update_singleton(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        *,
        global_speed_limit: int,
        park_threshold_min: int,
        alert_cooldown_s: int,
        hb_timeout_s: int,
        weather_city: str,
        map_center_lng: float,
        map_center_lat: float,
        transport_timeout_min: int,
        segment_buffer_min: int = 3,
    ) -> None:
        await conn.execute(
            UPDATE_BUSINESS_CONFIG_SQL,
            global_speed_limit,
            park_threshold_min,
            alert_cooldown_s,
            hb_timeout_s,
            weather_city.strip() or "Nanjing",
            map_center_lng,
            map_center_lat,
            transport_timeout_min,
            segment_buffer_min,
        )
