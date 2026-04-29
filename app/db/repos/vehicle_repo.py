from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import asyncpg

from app.core.exceptions import NotFoundError
from app.db.queries.vehicle import (
    INSERT_VEHICLE_SQL,
    SELECT_ALL_VEHICLES_SQL,
    SELECT_VEHICLE_BY_ID_SQL,
    SELECT_VEHICLES_BY_FLEET_SQL,
    SOFT_DELETE_VEHICLE_SQL,
    UPDATE_VEHICLE_SQL,
)


@dataclass(frozen=True)
class VehicleRow:
    id: int
    fleet_id: Optional[int]
    license_plate: str
    vehicle_type: str
    load_capacity: Optional[Decimal]
    notes: Optional[str]


class VehicleRepo:
    async def find_active(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        fleet_id: Optional[int],
    ) -> list[VehicleRow]:
        if fleet_id is None:
            rows = await conn.fetch(SELECT_ALL_VEHICLES_SQL)
        else:
            rows = await conn.fetch(SELECT_VEHICLES_BY_FLEET_SQL, fleet_id)
        return [_to_vehicle_row(r) for r in rows]

    async def find_by_id(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        vehicle_id: int,
    ) -> Optional[VehicleRow]:
        row = await conn.fetchrow(SELECT_VEHICLE_BY_ID_SQL, vehicle_id)
        return _to_vehicle_row(row) if row else None

    async def create(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        fleet_id: Optional[int],
        license_plate: str,
        vehicle_type: str = "",
        load_capacity: Optional[Decimal] = None,
        notes: Optional[str] = None,
    ) -> int:
        vehicle_id: int = await conn.fetchval(
            INSERT_VEHICLE_SQL, fleet_id, license_plate, vehicle_type, load_capacity, notes
        )
        return vehicle_id

    async def update(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        vehicle_id: int,
        license_plate: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        load_capacity: Optional[Decimal] = None,
        notes: Optional[str] = None,
        fleet_id: Optional[int] = None,
    ) -> None:
        await conn.execute(
            UPDATE_VEHICLE_SQL,
            vehicle_id, license_plate, vehicle_type, load_capacity, notes, fleet_id,
        )

    async def soft_delete(
        self, conn: asyncpg.Connection, vehicle_id: int  # type: ignore[type-arg]
    ) -> None:
        result = await conn.execute(SOFT_DELETE_VEHICLE_SQL, vehicle_id)
        if result == "UPDATE 0":
            raise NotFoundError("车辆不存在")


def _to_vehicle_row(row: asyncpg.Record) -> VehicleRow:  # type: ignore[type-arg]
    return VehicleRow(
        id=row["id"],
        fleet_id=row["fleet_id"],
        license_plate=row["license_plate"],
        vehicle_type=row["vehicle_type"],
        load_capacity=row["load_capacity"],
        notes=row["notes"],
    )
