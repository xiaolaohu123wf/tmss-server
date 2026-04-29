from __future__ import annotations

from typing import Optional

import asyncpg

from app.core.enums import ZoneType
from app.core.exceptions import NotFoundError
from app.db.repos.geo_zone_repo import GeoZoneRepo, GeoZoneRow
from app.models.http_geo_zone import GeoZoneCreate, GeoZoneResponse, GeoZoneUpdate

_repo = GeoZoneRepo()


def _to_response(row: GeoZoneRow) -> GeoZoneResponse:
    return GeoZoneResponse(
        id=row.id,
        name=row.name,
        zone_type=row.zone_type.value,
        coordinates=row.coordinates,
        speed_limit=row.speed_limit,
        dwell_min=row.dwell_min,
        is_enabled=row.is_enabled,
        extra=row.extra,
        notes=row.notes,
    )


class GeoZoneService:
    async def list_zones(
        self, conn: asyncpg.Connection  # type: ignore[type-arg]
    ) -> list[GeoZoneResponse]:
        rows = await _repo.find_all(conn)
        return [_to_response(r) for r in rows]

    async def get_zone(
        self, conn: asyncpg.Connection, zone_id: int  # type: ignore[type-arg]
    ) -> GeoZoneResponse:
        row = await _repo.find_by_id(conn, zone_id)
        if row is None:
            raise NotFoundError("围栏不存在")
        return _to_response(row)

    async def create_zone(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        body: GeoZoneCreate,
    ) -> GeoZoneResponse:
        new_id = await _repo.create(
            conn,
            name=body.name,
            zone_type=body.zone_type,
            coordinates=body.coordinates,
            speed_limit=body.speed_limit,
            dwell_min=body.dwell_min,
            is_enabled=body.is_enabled,
            notes=body.notes,
        )
        row = await _repo.find_by_id(conn, new_id)
        assert row is not None
        return _to_response(row)

    async def update_zone(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        zone_id: int,
        body: GeoZoneUpdate,
    ) -> GeoZoneResponse:
        row = await _repo.find_by_id(conn, zone_id)
        if row is None:
            raise NotFoundError("围栏不存在")
        await _repo.update(
            conn, zone_id,
            name=body.name,
            zone_type=body.zone_type,
            coordinates=body.coordinates,
            speed_limit=body.speed_limit,
            dwell_min=body.dwell_min,
            is_enabled=body.is_enabled,
            notes=body.notes,
        )
        updated = await _repo.find_by_id(conn, zone_id)
        assert updated is not None
        return _to_response(updated)

    async def delete_zone(
        self, conn: asyncpg.Connection, zone_id: int  # type: ignore[type-arg]
    ) -> None:
        await _repo.delete(conn, zone_id)
