from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

import asyncpg

from app.db.queries.operation_ban import SELECT_ENABLED_BANS_SQL


@dataclass(frozen=True)
class OperationBanRow:
    id: int
    zone_id: Optional[int]
    start_time: time
    end_time: time
    weekdays: list[int]


class OperationBanRepo:
    async def find_all_enabled(
        self, conn: asyncpg.Connection  # type: ignore[type-arg]
    ) -> list[OperationBanRow]:
        rows = await conn.fetch(SELECT_ENABLED_BANS_SQL)
        return [
            OperationBanRow(
                id=row["id"],
                zone_id=row["zone_id"],
                start_time=row["start_time"],
                end_time=row["end_time"],
                weekdays=list(row["weekdays"]),
            )
            for row in rows
        ]
