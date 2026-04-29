from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg

SELECT_ALL_FLEETS_SQL = """
    SELECT id, name, notes FROM fleet
    WHERE deleted_at IS NULL
    ORDER BY id
"""

SELECT_FLEET_BY_ID_SQL = """
    SELECT id, name, notes FROM fleet
    WHERE id = $1 AND deleted_at IS NULL
"""

SELECT_FLEET_BY_NAME_SQL = """
    SELECT id, name, notes FROM fleet
    WHERE name = $1 AND deleted_at IS NULL
"""

INSERT_FLEET_SQL = """
    INSERT INTO fleet (name, notes)
    VALUES ($1, $2)
    RETURNING id
"""

SOFT_DELETE_FLEET_SQL = """
    UPDATE fleet SET deleted_at = NOW()
    WHERE id = $1 AND deleted_at IS NULL
"""


@dataclass(frozen=True)
class FleetRow:
    id: int
    name: str
    notes: Optional[str]


class FleetRepo:
    async def find_all(
        self, conn: asyncpg.Connection  # type: ignore[type-arg]
    ) -> list[FleetRow]:
        rows = await conn.fetch(SELECT_ALL_FLEETS_SQL)
        return [_to_row(r) for r in rows]

    async def find_by_id(
        self, conn: asyncpg.Connection, fleet_id: int  # type: ignore[type-arg]
    ) -> Optional[FleetRow]:
        row = await conn.fetchrow(SELECT_FLEET_BY_ID_SQL, fleet_id)
        return _to_row(row) if row else None

    async def find_by_name(
        self, conn: asyncpg.Connection, name: str  # type: ignore[type-arg]
    ) -> Optional[FleetRow]:
        row = await conn.fetchrow(SELECT_FLEET_BY_NAME_SQL, name)
        return _to_row(row) if row else None

    async def create(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        name: str,
        notes: Optional[str] = None,
    ) -> int:
        fleet_id: int = await conn.fetchval(INSERT_FLEET_SQL, name, notes)
        return fleet_id

    async def soft_delete(
        self, conn: asyncpg.Connection, fleet_id: int  # type: ignore[type-arg]
    ) -> None:
        await conn.execute(SOFT_DELETE_FLEET_SQL, fleet_id)


def _to_row(row: asyncpg.Record) -> FleetRow:  # type: ignore[type-arg]
    return FleetRow(id=row["id"], name=row["name"], notes=row["notes"])
