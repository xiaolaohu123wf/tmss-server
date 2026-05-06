from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import os
import struct
import zlib

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.cache.pool import close_redis_pool, init_redis
from app.config import settings
from app.db.pool import close_pool, get_pool
from app.http.error_handler import register_error_handlers

logger = structlog.get_logger()


def _make_transparent_png() -> bytes:
    """Generate a minimal 1×1 fully-transparent RGBA PNG at import time."""

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1×1 RGBA
    idat_data = zlib.compress(b"\x00\x00\x00\x00\x00")  # filter=None + RGBA(0,0,0,0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr_data)
        + _chunk(b"IDAT", idat_data)
        + _chunk(b"IEND", b"")
    )


_TRANSPARENT_PNG: bytes = _make_transparent_png()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ── 启动 ──────────────────────────────────
    await logger.ainfo("app_startup")
    pool = await get_pool()
    await init_redis()

    # 首次启动：若无管理员账号，自动创建 admin/admin123
    await _ensure_default_admin(pool)

    # 清除旧的天气缓存（防止修改映射规则后旧值继续生效）
    from app.cache.pool import get_redis as _get_redis
    try:
        await _get_redis().delete("weather:current")
    except Exception:
        pass

    # 启动时立即清理一次残留的超时开放段（处理上次意外重启遗留的未关段）
    from app.services.segment_sweeper import close_stale_segments_once, segment_sweeper_loop
    try:
        n = await close_stale_segments_once()
        if n:
            await logger.ainfo("startup_stale_segments_fixed", count=n)
    except Exception as exc:
        await logger.awarning("startup_stale_segments_skip", error=str(exc))

    # 后台任务：定期关闭超时轨迹段（弥补断线未触发关段的情况）
    from app.core.task_registry import task_registry
    task_registry.spawn(segment_sweeper_loop(), name="segment-sweeper")

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
    from app.http.routers.router_fleets import router as router_fleets
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
    app.include_router(router_fleets)
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

        @app.get("/orthophoto-test", include_in_schema=False)
        async def orthophoto_amap_test_page() -> FileResponse:
            return FileResponse(os.path.join(_static_dir, "orthophoto_amap_test.html"))

        @app.exception_handler(StarletteHTTPException)
        async def _tile_404_handler(request: Request, exc: StarletteHTTPException) -> Response:
            """Return a transparent PNG instead of 404 for missing DOM tiles.
            Prevents AMap TileLayer from flooding the console with 404 errors
            for tiles outside the orthophoto coverage area."""
            path = request.url.path
            if (
                exc.status_code == 404
                and "/tiles_dom/" in path
                and (path.endswith(".png") or path.endswith(".jpg"))
            ):
                return Response(content=_TRANSPARENT_PNG, media_type="image/png")
            from fastapi.exception_handlers import http_exception_handler
            return await http_exception_handler(request, exc)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    # ── 前端 SPA 托管（生产模式）─────────────────────────────────────────
    # 当 frontend/dist 存在时，将打包产物挂载到 HTTP 服务，避免额外部署 nginx。
    # /assets 静态资源直接从磁盘返回；其余路径（非 /api）返回 index.html（SPA 路由兜底）。
    _dist_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    _dist_dir = os.path.normpath(_dist_dir)
    if os.path.isdir(_dist_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(_dist_dir, "assets")), name="vue-assets")

        _index_html = os.path.join(_dist_dir, "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:  # noqa: ARG001
            """SPA 路由兜底：任何非 /api/* 路径都返回 index.html，交由 Vue Router 处理。"""
            return FileResponse(_index_html)

    return app
