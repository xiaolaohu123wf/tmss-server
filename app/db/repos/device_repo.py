from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

from app.db.queries.device import (
    INSERT_BIND_SQL,
    INSERT_DEVICE_SQL,
    SELECT_ACTIVE_BIND_BY_DEVICE_SQL,
    SELECT_ACTIVE_BIND_BY_VEHICLE_SQL,
    SELECT_ALL_DEVICES_SQL,
    SELECT_DEVICE_BY_ID_SQL,
    SELECT_DEVICE_BY_IMEI_SQL,
    SOFT_DELETE_DEVICE_SQL,
    UNBIND_SQL,
    UPDATE_DEVICE_FIRMWARE_SQL,
)


@dataclass(frozen=True)
class DeviceRow:
    id: int
    imei: str
    iccid: Optional[str]
    model: Optional[str]
    firmware_version: Optional[str]
    notes: Optional[str]


@dataclass(frozen=True)
class BindRow:
    id: int
    device_id: int
    vehicle_id: int
    driver_id: Optional[int]
    bound_at: datetime
    operator: Optional[str]


class DeviceRepo:
    async def find_by_imei(
        self, conn: asyncpg.Connection, imei: str  # type: ignore[type-arg]
    ) -> Optional[DeviceRow]:
        row = await conn.fetchrow(SELECT_DEVICE_BY_IMEI_SQL, imei)
        return _to_device_row(row) if row else None

    async def find_by_id(
        self, conn: asyncpg.Connection, device_id: int  # type: ignore[type-arg]
    ) -> Optional[DeviceRow]:
        row = await conn.fetchrow(SELECT_DEVICE_BY_ID_SQL, device_id)
        return _to_device_row(row) if row else None

    async def find_all(
        self, conn: asyncpg.Connection  # type: ignore[type-arg]
    ) -> list[DeviceRow]:
        rows = await conn.fetch(SELECT_ALL_DEVICES_SQL)
        return [_to_device_row(r) for r in rows]

    async def create(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        imei: str,
        iccid: Optional[str] = None,
        model: Optional[str] = None,
        firmware_version: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> int:
        device_id: int = await conn.fetchval(
            INSERT_DEVICE_SQL, imei, iccid, model, firmware_version, notes
        )
        return device_id

    async def update_firmware(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        device_id: int,
        firmware_version: str,
        iccid: Optional[str] = None,
    ) -> None:
        await conn.execute(UPDATE_DEVICE_FIRMWARE_SQL, device_id, firmware_version, iccid)

    async def soft_delete(
        self, conn: asyncpg.Connection, device_id: int  # type: ignore[type-arg]
    ) -> None:
        await conn.execute(SOFT_DELETE_DEVICE_SQL, device_id)

    async def get_active_bind_by_device(
        self, conn: asyncpg.Connection, device_id: int  # type: ignore[type-arg]
    ) -> Optional[BindRow]:
        row = await conn.fetchrow(SELECT_ACTIVE_BIND_BY_DEVICE_SQL, device_id)
        return _to_bind_row(row) if row else None

    async def get_active_bind_by_vehicle(
        self, conn: asyncpg.Connection, vehicle_id: int  # type: ignore[type-arg]
    ) -> Optional[BindRow]:
        row = await conn.fetchrow(SELECT_ACTIVE_BIND_BY_VEHICLE_SQL, vehicle_id)
        return _to_bind_row(row) if row else None

    async def bind(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        device_id: int,
        vehicle_id: int,
        driver_id: Optional[int] = None,
        operator: Optional[str] = None,
    ) -> int:
        bind_id: int = await conn.fetchval(INSERT_BIND_SQL, device_id, vehicle_id, driver_id, operator)
        return bind_id

    async def unbind(
        self, conn: asyncpg.Connection, device_id: int  # type: ignore[type-arg]
    ) -> None:
        await conn.execute(UNBIND_SQL, device_id)


def _to_device_row(row: asyncpg.Record) -> DeviceRow:  # type: ignore[type-arg]
    return DeviceRow(
        id=row["id"],
        imei=row["imei"],
        iccid=row["iccid"],
        model=row["model"],
        firmware_version=row["firmware_version"],
        notes=row["notes"],
    )


def _to_bind_row(row: asyncpg.Record) -> BindRow:  # type: ignore[type-arg]
    return BindRow(
        id=row["id"],
        device_id=row["device_id"],
        vehicle_id=row["vehicle_id"],
        driver_id=row["driver_id"],
        bound_at=row["bound_at"],
        operator=row["operator"],
    )
