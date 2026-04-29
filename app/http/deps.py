from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Optional

import asyncpg
from fastapi import Depends, Request
from redis.asyncio import Redis

from app.cache.pool import get_redis
from app.cache.session_repo import SessionData, SessionRepo
from app.core.enums import UserRole
from app.core.exceptions import PermissionDeniedError
from app.db.deps import get_db_conn
from app.services.auth_service import AuthService

COOKIE_NAME = "tmss_session"

_session_repo = SessionRepo()
_auth_service = AuthService()


async def require_auth(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> SessionData:
    session_id: Optional[str] = request.cookies.get(COOKIE_NAME)
    if not session_id:
        raise PermissionDeniedError("未登录")

    session = await _session_repo.get(redis, session_id)
    if session is None:
        raise PermissionDeniedError("会话已过期，请重新登录")

    if _session_repo.is_expired(session):
        await _session_repo.delete(redis, session_id)
        raise PermissionDeniedError("会话已过期，请重新登录")

    # 每次请求滑动续期
    await _session_repo.refresh(redis, session_id)
    return session


async def require_manager(
    session: SessionData = Depends(require_auth),
) -> SessionData:
    if session.role != UserRole.MANAGER:
        raise PermissionDeniedError("需要管理员权限")
    return session


async def require_fleet_or_above(
    session: SessionData = Depends(require_auth),
) -> SessionData:
    """车队长及以上（fleet_captain 或 manager）。"""
    if session.role not in (UserRole.MANAGER, UserRole.FLEET_CAPTAIN):
        raise PermissionDeniedError("权限不足")
    return session


async def require_password_confirm(
    request: Request,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> SessionData:
    """高危操作的二次密码验证，从 X-Confirm-Password 请求头读取。"""
    pw = request.headers.get("X-Confirm-Password")
    if not pw:
        raise PermissionDeniedError("高危操作需要二次密码确认")
    verified = await _auth_service.verify_password(conn, session.user_id, pw)
    if not verified:
        raise PermissionDeniedError("管理员密码确认失败")
    return session
