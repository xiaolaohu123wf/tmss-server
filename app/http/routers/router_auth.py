from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Request, Response
from redis.asyncio import Redis

from app.cache.pool import get_redis
from app.cache.session_repo import SessionData
from app.db.deps import get_db_conn
from app.http.deps import COOKIE_NAME, require_auth
from app.http.response import ok
from app.models.http_user import LoginRequest, LoginResponse
from app.services.auth_service import AuthService

logger = structlog.get_logger()
router = APIRouter(prefix="/api/auth", tags=["auth"])
_auth_service = AuthService()


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
    redis: Redis = Depends(get_redis),
) -> dict:
    session_id, session = await _auth_service.login(conn, redis, body.username, body.password)

    response.set_cookie(
        key=COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=86400,
    )

    return ok(LoginResponse(
        user_id=session.user_id,
        username=session.username,
        role=session.role.value,
        fleet_id=session.fleet_id,
    ))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: SessionData = Depends(require_auth),
    redis: Redis = Depends(get_redis),
) -> dict:
    session_id = request.cookies.get(COOKIE_NAME)
    await _auth_service.logout(redis, session_id)
    response.delete_cookie(key=COOKIE_NAME)
    return ok({"message": "已退出登录"})


@router.get("/me")
async def me(session: SessionData = Depends(require_auth)) -> dict:
    return ok(LoginResponse(
        user_id=session.user_id,
        username=session.username,
        role=session.role.value,
        fleet_id=session.fleet_id,
    ))
