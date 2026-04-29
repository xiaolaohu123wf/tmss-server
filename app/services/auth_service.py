from __future__ import annotations

from typing import Optional

import asyncpg
import structlog
from redis.asyncio import Redis

from app.cache.session_repo import SessionData, SessionRepo
from app.core.enums import UserRole
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.db.repos.user_repo import UserRepo

logger = structlog.get_logger()

_user_repo = UserRepo()
_session_repo = SessionRepo()


class AuthService:
    async def login(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        redis: Redis,
        username: str,
        password: str,
    ) -> tuple[str, SessionData]:
        """
        验证用户名/密码，创建 Session。
        返回 (session_id, SessionData)。
        """
        user = await _user_repo.find_by_username(conn, username)
        if user is None or not user.is_active:
            raise PermissionDeniedError("用户名或密码错误")

        ok = await _user_repo.verify_password(conn, user.id, password)
        if not ok:
            raise PermissionDeniedError("用户名或密码错误")

        session_id = await _session_repo.create(
            redis,
            user_id=user.id,
            username=user.username,
            role=user.role,
            fleet_id=user.fleet_id,
        )
        session = await _session_repo.get(redis, session_id)
        assert session is not None  # 刚写入，不可能为 None

        await logger.ainfo("user_login", user_id=user.id, username=username, role=user.role.value)
        return session_id, session

    async def logout(self, redis: Redis, session_id: Optional[str]) -> None:
        if session_id:
            await _session_repo.delete(redis, session_id)

    async def verify_password(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        user_id: int,
        password: str,
    ) -> bool:
        try:
            return await _user_repo.verify_password(conn, user_id, password)
        except NotFoundError:
            return False
