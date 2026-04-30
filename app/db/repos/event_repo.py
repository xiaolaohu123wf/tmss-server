from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import asyncpg

from app.core.enums import EventType
from app.db.queries.event import (
    COUNT_EVENTS_ALL_SQL,
    COUNT_EVENTS_BY_VEHICLE_SQL,
    COUNT_EVENTS_PAGE_SQL,
    INSERT_EVENT_SQL,
    SELECT_EVENTS_ALL_SQL,
    SELECT_EVENTS_BY_VEHICLE_SQL,
    SELECT_EVENTS_PAGE_SQL,
)


@dataclass(frozen=True)
class EventRow:
    id: int
    device_id: Optional[int]
    vehicle_id: Optional[int]
    event_type: str
    severity: int
    zone_id: Optional[int]
    lat: Optional[float]
    lng: Optional[float]
    speed: Optional[float]
    cmd_sent: Optional[str]
    detail: Optional[dict[str, Any]]
    occurred_at: datetime
    vehicle_license: Optional[str] = None


class EventRepo:
    async def insert(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        event_type: EventType,
        occurred_at: datetime,
        device_id: Optional[int] = None,
        vehicle_id: Optional[int] = None,
        severity: int = 2,
        zone_id: Optional[int] = None,
        ban_id: Optional[int] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        speed: Optional[float] = None,
        cmd_sent: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> int:
        import json
        detail_json = json.dumps(detail) if detail is not None else None
        event_id: int = await conn.fetchval(
            INSERT_EVENT_SQL,
            device_id, vehicle_id, event_type.value, severity,
            zone_id, ban_id, lat, lng, speed, cmd_sent, detail_json, occurred_at,
        )
        return event_id

    async def find_by_vehicle(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        vehicle_id: int,
        start: datetime,
        end: datetime,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EventRow]:
        rows = await conn.fetch(SELECT_EVENTS_BY_VEHICLE_SQL, vehicle_id, start, end, limit, offset)
        return [_to_event_row(r) for r in rows]

    async def find_all(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        start: datetime,
        end: datetime,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EventRow]:
        rows = await conn.fetch(SELECT_EVENTS_ALL_SQL, start, end, limit, offset)
        return [_to_event_row(r) for r in rows]

    async def count_by_vehicle(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        vehicle_id: int,
        start: datetime,
        end: datetime,
    ) -> int:
        return int(await conn.fetchval(COUNT_EVENTS_BY_VEHICLE_SQL, vehicle_id, start, end))

    async def count_all(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        start: datetime,
        end: datetime,
    ) -> int:
        return int(await conn.fetchval(COUNT_EVENTS_ALL_SQL, start, end))

    async def find_page(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        fleet_id: Optional[int] = None,
        vehicle_id: Optional[int] = None,
        event_type: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[int, list[EventRow]]:
        offset = (page - 1) * size
        total = int(await conn.fetchval(
            COUNT_EVENTS_PAGE_SQL,
            vehicle_id, event_type, start, end, fleet_id,
        ))
        rows = await conn.fetch(
            SELECT_EVENTS_PAGE_SQL,
            vehicle_id, event_type, start, end, fleet_id, size, offset,
        )
        return total, [_to_event_row(r) for r in rows]


def _to_event_row(row: asyncpg.Record) -> EventRow:  # type: ignore[type-arg]
    import json
    detail = row["detail"]
    if isinstance(detail, str):
        detail = json.loads(detail)
    keys = row.keys()
    return EventRow(
        id=row["id"],
        device_id=row["device_id"],
        vehicle_id=row["vehicle_id"],
        event_type=row["event_type"],
        severity=row["severity"],
        zone_id=row["zone_id"],
        lat=float(row["lat"]) if row["lat"] is not None else None,
        lng=float(row["lng"]) if row["lng"] is not None else None,
        speed=float(row["speed"]) if row["speed"] is not None else None,
        cmd_sent=row["cmd_sent"],
        detail=detail,
        occurred_at=row["occurred_at"],
        vehicle_license=row["vehicle_license"] if "vehicle_license" in keys else None,
    )
