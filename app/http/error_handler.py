from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import TmssError

logger = structlog.get_logger()


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(TmssError)
    async def tmss_error_handler(request: Request, exc: TmssError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"ok": False, "code": exc.code, "message": exc.message},
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_error_handler(
        request: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        # 取第一条可读说明（含 model_validator 的 ValueError 文案）
        message = "请求参数校验失败"
        if errors:
            first = errors[0]
            msg = str(first.get("msg") or "")
            if msg:
                message = msg
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "code": "validation_error",
                "message": message,
                "detail": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"ok": False, "code": "internal_error", "message": "服务器内部错误"},
        )
