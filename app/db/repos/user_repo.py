from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import asyncpg
import bcrypt

from app.core.enums import UserRole
from app.core.exceptions import NotFoundError
from app.db.queries.user import (
    DEACTIVATE_USER_SQL,
    INSERT_USER_SQL,
    SELECT_ALL_USERS_SQL,
    SELECT_USER_BY_ID_SQL,
    SELECT_USER_BY_USERNAME_SQL,
    SOFT_DELETE_USER_SQL,
    UPDATE_PASSWORD_SQL,
    UPDATE_USER_SQL,
)


@dataclass(frozen=True)
class UserRow:
    id: int
    username: str
    password_hash: str
    role: UserRole
    fleet_id: Optional[int]
    is_active: bool


class UserRepo:
    async def find_by_username(
        self, conn: asyncpg.Connection, username: str  # type: ignore[type-arg]
    ) -> Optional[UserRow]:
        row = await conn.fetchrow(SELECT_USER_BY_USERNAME_SQL, username)
        return UserRow(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=UserRole(row["role"]),
            fleet_id=row["fleet_id"],
            is_active=row["is_active"],
        ) if row else None

    async def find_by_id(
        self, conn: asyncpg.Connection, user_id: int  # type: ignore[type-arg]
    ) -> Optional[UserRow]:
        row = await conn.fetchrow(SELECT_USER_BY_ID_SQL, user_id)
        return UserRow(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            role=UserRole(row["role"]),
            fleet_id=row["fleet_id"],
            is_active=row["is_active"],
        ) if row else None

    async def find_all(
        self, conn: asyncpg.Connection  # type: ignore[type-arg]
    ) -> list[UserRow]:
        rows = await conn.fetch(SELECT_ALL_USERS_SQL)
        return [
            UserRow(
                id=r["id"],
                username=r["username"],
                password_hash="",
                role=UserRole(r["role"]),
                fleet_id=r["fleet_id"],
                is_active=r["is_active"],
            )
            for r in rows
        ]

    async def create(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        username: str,
        plain_password: str,
        role: UserRole,
        fleet_id: Optional[int] = None,
        bcrypt_cost: int = 12,
    ) -> int:
        hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt(rounds=bcrypt_cost))
        user_id: int = await conn.fetchval(
            INSERT_USER_SQL, username, hashed.decode(), role.value, fleet_id
        )
        return user_id

    async def verify_password(
        self, conn: asyncpg.Connection, user_id: int, plain_password: str  # type: ignore[type-arg]
    ) -> bool:
        row = await conn.fetchrow(SELECT_USER_BY_ID_SQL, user_id)
        if not row:
            raise NotFoundError("用户不存在")
        return bcrypt.checkpw(plain_password.encode(), row["password_hash"].encode())

    async def update(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        user_id: int,
        is_active: Optional[bool] = None,
        fleet_id: Optional[int] = None,
    ) -> None:
        await conn.execute(UPDATE_USER_SQL, user_id, is_active, fleet_id)

    async def soft_delete(
        self, conn: asyncpg.Connection, user_id: int  # type: ignore[type-arg]
    ) -> None:
        await conn.execute(SOFT_DELETE_USER_SQL, user_id)

    async def deactivate(
        self, conn: asyncpg.Connection, user_id: int  # type: ignore[type-arg]
    ) -> None:
        await conn.execute(DEACTIVATE_USER_SQL, user_id)

    async def update_password(
        self, conn: asyncpg.Connection, user_id: int, plain_password: str  # type: ignore[type-arg]
    ) -> None:
        hashed = bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt(rounds=12))
        await conn.execute(UPDATE_PASSWORD_SQL, user_id, hashed.decode())
