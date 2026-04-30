from __future__ import annotations

from typing import Optional

import asyncpg

from app.db.queries.command_log import (
    INSERT_COMMAND_LOG_SQL,
    UPDATE_COMMAND_DELIVERED_SQL,
)


class CommandLogRepo:
    async def insert(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        cmd: str,
        device_id: Optional[int] = None,
        vehicle_id: Optional[int] = None,
        source: str = "auto",
        operator_id: Optional[int] = None,
        event_id: Optional[int] = None,
        speed_kmh: Optional[float] = None,
    ) -> int:
        log_id: int = await conn.fetchval(
            INSERT_COMMAND_LOG_SQL,
            device_id, vehicle_id, cmd, source, operator_id, event_id, speed_kmh,
        )
        return log_id

    async def mark_delivered(
        self, conn: asyncpg.Connection, log_id: int  # type: ignore[type-arg]
    ) -> None:
        await conn.execute(UPDATE_COMMAND_DELIVERED_SQL, log_id)
