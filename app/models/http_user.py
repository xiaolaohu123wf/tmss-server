from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.core.enums import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    user_id: int
    username: str
    role: str
    fleet_id: Optional[int]


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6)
    role: UserRole = UserRole.FLEET_CAPTAIN
    fleet_id: Optional[int] = None


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    fleet_id: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    fleet_id: Optional[int]
    is_active: bool
