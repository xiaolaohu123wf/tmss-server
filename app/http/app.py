from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import os

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.cache.pool import close_redis_pool, init_redis
from app.config import settings
from app.db.pool import close_pool, get_pool
from app.http.error_handler import register_error_handlers

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ── 启动 ──────────────────────────────────
    await logger.ainfo("app_startup")
    pool = await get_pool()
    await init_redis()

    # 首次启动：若无管理员账号，自动创建 admin/admin123
    await _ensure_default_admin(pool)

    yield

    # ── 关闭 ──────────────────────────────────
    from app.core.task_registry import task_registry
    await task_registry.shutdown()
    await close_pool()
    await close_redis_pool()
    await logger.ainfo("app_shutdown")


async def _ensure_default_admin(pool) -> None:  # type: ignore[no-untyped-def]
    from app.core.enums import UserRole
    from app.db.repos.user_repo import UserRepo

    repo = UserRepo()
    async with pool.acquire() as conn:
        existing = await repo.find_by_username(conn, "admin")
        if existing is None:
            await repo.create(
                conn,
                username="admin",
                plain_password="admin123",
                role=UserRole.MANAGER,
                bcrypt_cost=settings.bcrypt_cost,
            )
            await logger.ainfo("default_admin_created", username="admin")


def create_app() -> FastAPI:
    app = FastAPI(
        title="TMSS API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    register_error_handlers(app)

    # ── 路由注册 ──────────────────────────────
    from app.http.routers import router_auth
    from app.http.routers.router_vehicles import router as router_vehicles
    from app.http.routers.router_devices import router as router_devices
    from app.http.routers.router_geo_zones import router as router_geo_zones
    from app.http.routers.router_events import router as router_events
    from app.http.routers.router_users import router as router_users
    from app.http.routers.router_admin import router as router_admin
    from app.http.routers.router_tcp_messages import router as router_tcp_messages
    from app.http.routers.router_stream import router as router_stream
    from app.http.routers.router_track_segments import router as router_track_segments

    app.include_router(router_auth.router)
    app.include_router(router_vehicles)
    app.include_router(router_devices)
    app.include_router(router_geo_zones)
    app.include_router(router_events)
    app.include_router(router_users)
    app.include_router(router_admin)
    app.include_router(router_tcp_messages)
    app.include_router(router_stream)
    app.include_router(router_track_segments)

    # 监控页面
    _static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
    _static_dir = os.path.normpath(_static_dir)
    if os.path.isdir(_static_dir):
        app.mount("/static", StaticFiles(directory=_static_dir), name="static")

        @app.get("/monitor", include_in_schema=False)
        async def monitor_page() -> FileResponse:
            return FileResponse(os.path.join(_static_dir, "monitor.html"))

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app
