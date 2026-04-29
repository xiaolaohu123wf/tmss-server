from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import asyncpg

from app.core.enums import ZoneType
from app.core.exceptions import NotFoundError
from app.db.queries.geo_zone import (
    DELETE_ZONE_SQL,
    INSERT_ZONE_SQL,
    SELECT_ALL_ENABLED_ZONES_SQL,
    SELECT_ALL_ZONES_SQL,
    SELECT_ZONE_BY_ID_SQL,
    UPDATE_ZONE_SQL,
)


@dataclass(frozen=True)
class GeoZoneRow:
    id: int
    name: str
    zone_type: ZoneType
    coordinates: list[list[float]]
    speed_limit: Optional[int]
    dwell_min: Optional[int]
    is_enabled: bool
    extra: Optional[dict[str, Any]]
    notes: Optional[str]


class GeoZoneRepo:
    async def find_all_enabled(
        self, conn: asyncpg.Connection  # type: ignore[type-arg]
    ) -> list[GeoZoneRow]:
        rows = await conn.fetch(SELECT_ALL_ENABLED_ZONES_SQL)
        return [_to_zone_row(r) for r in rows]

    async def find_all(
        self, conn: asyncpg.Connection  # type: ignore[type-arg]
    ) -> list[GeoZoneRow]:
        rows = await conn.fetch(SELECT_ALL_ZONES_SQL)
        return [_to_zone_row(r) for r in rows]

    async def find_by_id(
        self, conn: asyncpg.Connection, zone_id: int  # type: ignore[type-arg]
    ) -> Optional[GeoZoneRow]:
        row = await conn.fetchrow(SELECT_ZONE_BY_ID_SQL, zone_id)
        return _to_zone_row(row) if row else None

    async def create(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        name: str,
        zone_type: ZoneType,
        coordinates: list[list[float]],
        speed_limit: Optional[int] = None,
        dwell_min: Optional[int] = None,
        is_enabled: bool = True,
        notes: Optional[str] = None,
    ) -> int:
        zone_id: int = await conn.fetchval(
            INSERT_ZONE_SQL,
            name, zone_type.value, json.dumps(coordinates),
            speed_limit, dwell_min, is_enabled, notes,
        )
        return zone_id

    async def update(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        zone_id: int,
        name: Optional[str] = None,
        zone_type: Optional[ZoneType] = None,
        coordinates: Optional[list[list[float]]] = None,
        speed_limit: Optional[int] = None,
        dwell_min: Optional[int] = None,
        is_enabled: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> None:
        coords_json = json.dumps(coordinates) if coordinates is not None else None
        zone_type_val = zone_type.value if zone_type is not None else None
        await conn.execute(
            UPDATE_ZONE_SQL,
            zone_id, name, zone_type_val, coords_json,
            speed_limit, dwell_min, is_enabled, notes,
        )

    async def delete(
        self, conn: asyncpg.Connection, zone_id: int  # type: ignore[type-arg]
    ) -> None:
        result = await conn.execute(DELETE_ZONE_SQL, zone_id)
        if result == "DELETE 0":
            raise NotFoundError("围栏不存在")


def _to_zone_row(row: asyncpg.Record) -> GeoZoneRow:  # type: ignore[type-arg]
    coords = row["coordinates"]
    if isinstance(coords, str):
        coords = json.loads(coords)

    extra = row["extra"]
    if isinstance(extra, str):
        extra = json.loads(extra)

    return GeoZoneRow(
        id=row["id"],
        name=row["name"],
        zone_type=ZoneType(row["zone_type"]),
        coordinates=coords,
        speed_limit=row["speed_limit"],
        dwell_min=row["dwell_min"],
        is_enabled=row["is_enabled"],
        extra=extra,
        notes=row["notes"],
    )
