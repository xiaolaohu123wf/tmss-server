from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg

from app.db.pool import get_pool


async def get_db_conn() -> AsyncIterator[asyncpg.Connection]:  # type: ignore[type-arg]
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
