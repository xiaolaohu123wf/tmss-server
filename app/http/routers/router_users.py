from __future__ import annotations

from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends

from app.cache.session_repo import SessionData
from app.core.enums import UserRole
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.db.deps import get_db_conn
from app.db.repos.user_repo import UserRepo
from app.http.deps import require_auth, require_manager
from app.http.response import ok
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/users", tags=["users"])
_repo = UserRepo()


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=6)
    role: UserRole = UserRole.FLEET_CAPTAIN
    fleet_id: Optional[int] = None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6)


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    fleet_id: Optional[int]
    is_active: bool


@router.get("")
async def list_users(
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    rows = await _repo.find_all(conn)
    return ok([UserResponse(
        id=r.id, username=r.username, role=r.role.value,
        fleet_id=r.fleet_id, is_active=r.is_active,
    ).model_dump() for r in rows])


@router.post("")
async def create_user(
    body: UserCreateRequest,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    existing = await _repo.find_by_username(conn, body.username)
    if existing is not None:
        raise ValidationError("用户名已存在")
    new_id = await _repo.create(
        conn,
        username=body.username,
        plain_password=body.password,
        role=body.role,
        fleet_id=body.fleet_id,
    )
    row = await _repo.find_by_id(conn, new_id)
    assert row is not None
    return ok(UserResponse(
        id=row.id, username=row.username, role=row.role.value,
        fleet_id=row.fleet_id, is_active=row.is_active,
    ).model_dump())


@router.put("/{user_id}/password")
async def change_password(
    user_id: int,
    body: PasswordChangeRequest,
    session: SessionData = Depends(require_auth),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    # 只允许用户修改自己的密码，manager 可以修改任意用户
    if session.role != UserRole.MANAGER and session.user_id != user_id:
        raise PermissionDeniedError("无权修改他人密码")

    row = await _repo.find_by_id(conn, user_id)
    if row is None:
        raise NotFoundError("用户不存在")

    valid = await _repo.verify_password(conn, user_id, body.old_password)
    if not valid:
        raise ValidationError("原密码错误")

    await _repo.update_password(conn, user_id, body.new_password)
    return ok({"message": "密码已更新"})


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: int,
    session: SessionData = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    if session.user_id == user_id:
        raise ValidationError("不能删除自己")
    row = await _repo.find_by_id(conn, user_id)
    if row is None:
        raise NotFoundError("用户不存在")
    await _repo.soft_delete(conn, user_id)
    return ok({"message": "用户已删除"})
