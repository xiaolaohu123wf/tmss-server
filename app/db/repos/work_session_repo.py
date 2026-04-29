from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

from app.core.enums import WorkState
from app.db.queries.work_session import (
    CLOSE_WORK_SESSION_SQL,
    INSERT_WORK_SESSION_SQL,
    SELECT_OPEN_SESSION_BY_VEHICLE_SQL,
)


@dataclass(frozen=True)
class WorkSessionRow:
    id: int
    vehicle_id: int
    state: WorkState
    zone_id: Optional[int]
    started_at: datetime


class WorkSessionRepo:
    async def open_session(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        vehicle_id: int,
        state: WorkState,
        zone_id: Optional[int] = None,
    ) -> int:
        session_id: int = await conn.fetchval(INSERT_WORK_SESSION_SQL, vehicle_id, state.value, zone_id)
        return session_id

    async def close_session(
        self, conn: asyncpg.Connection, session_id: int  # type: ignore[type-arg]
    ) -> None:
        await conn.execute(CLOSE_WORK_SESSION_SQL, session_id)

    async def find_open_by_vehicle(
        self, conn: asyncpg.Connection, vehicle_id: int  # type: ignore[type-arg]
    ) -> Optional[WorkSessionRow]:
        row = await conn.fetchrow(SELECT_OPEN_SESSION_BY_VEHICLE_SQL, vehicle_id)
        if not row:
            return None
        return WorkSessionRow(
            id=row["id"],
            vehicle_id=row["vehicle_id"],
            state=WorkState(row["state"]),
            zone_id=row["zone_id"],
            started_at=row["started_at"],
        )
