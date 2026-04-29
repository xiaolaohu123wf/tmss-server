from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis

from app.core.enums import UserRole

SESSION_PREFIX = "session:"
SESSION_TTL_SECONDS = 86400  # 24 小时


@dataclass
class SessionData:
    user_id: int
    username: str
    role: UserRole
    fleet_id: Optional[int]
    issued_at: str   # ISO 格式字符串，便于 JSON 序列化
    expires_at: str


class SessionRepo:
    async def create(
        self,
        redis: Redis,
        user_id: int,
        username: str,
        role: UserRole,
        fleet_id: Optional[int] = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        expires = now + timedelta(seconds=SESSION_TTL_SECONDS)

        data = SessionData(
            user_id=user_id,
            username=username,
            role=role,
            fleet_id=fleet_id,
            issued_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )
        payload = asdict(data)
        payload["role"] = role.value

        await redis.set(
            SESSION_PREFIX + session_id,
            json.dumps(payload),
            ex=SESSION_TTL_SECONDS,
        )
        return session_id

    async def get(self, redis: Redis, session_id: str) -> Optional[SessionData]:
        raw = await redis.get(SESSION_PREFIX + session_id)
        if not raw:
            return None
        payload = json.loads(raw)
        return SessionData(
            user_id=payload["user_id"],
            username=payload["username"],
            role=UserRole(payload["role"]),
            fleet_id=payload["fleet_id"],
            issued_at=payload["issued_at"],
            expires_at=payload["expires_at"],
        )

    async def refresh(self, redis: Redis, session_id: str) -> None:
        """每次请求滑动续期。"""
        await redis.expire(SESSION_PREFIX + session_id, SESSION_TTL_SECONDS)

    async def delete(self, redis: Redis, session_id: str) -> None:
        await redis.delete(SESSION_PREFIX + session_id)

    def is_expired(self, session: SessionData) -> bool:
        expires = datetime.fromisoformat(session.expires_at)
        return datetime.now(timezone.utc) >= expires
