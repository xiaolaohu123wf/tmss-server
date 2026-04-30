from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg

from app.db.queries.business_config import SELECT_BUSINESS_CONFIG_SQL

UPDATE_BUSINESS_CONFIG_SQL = """
    UPDATE business_config SET
        global_speed_limit = $1,
        park_threshold_min = $2,
        loading_dwell_min = $3,
        unloading_dwell_min = $4,
        alert_cooldown_s = $5,
        hb_timeout_s = $6,
        weather_city = $7
    WHERE id = 1
"""


@dataclass(frozen=True)
class BusinessConfigRow:
    global_speed_limit: int
    park_threshold_min: int
    loading_dwell_min: int
    unloading_dwell_min: int
    alert_cooldown_s: int
    hb_timeout_s: int
    weather_city: str


def _row_from_record(r: asyncpg.Record) -> BusinessConfigRow:  # type: ignore[name-defined]
    return BusinessConfigRow(
        global_speed_limit=int(r["global_speed_limit"]),
        park_threshold_min=int(r["park_threshold_min"]),
        loading_dwell_min=int(r["loading_dwell_min"]),
        unloading_dwell_min=int(r["unloading_dwell_min"]),
        alert_cooldown_s=int(r["alert_cooldown_s"]),
        hb_timeout_s=int(r["hb_timeout_s"]),
        weather_city=str(r["weather_city"]),
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
        loading_dwell_min: int,
        unloading_dwell_min: int,
        alert_cooldown_s: int,
        hb_timeout_s: int,
        weather_city: str,
    ) -> None:
        await conn.execute(
            UPDATE_BUSINESS_CONFIG_SQL,
            global_speed_limit,
            park_threshold_min,
            loading_dwell_min,
            unloading_dwell_min,
            alert_cooldown_s,
            hb_timeout_s,
            weather_city.strip() or "Nanjing",
        )
