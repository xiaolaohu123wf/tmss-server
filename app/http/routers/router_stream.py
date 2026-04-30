from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.cache.session_repo import SessionData
from app.core.event_bus import event_bus
from app.http.deps import require_auth

router = APIRouter(prefix="/api/stream", tags=["stream"])

_KEEPALIVE_INTERVAL = 25  # 秒


async def _sse_generator(
    request: Request,
    topics: list[str],
) -> AsyncGenerator[str, None]:
    """订阅指定 topic 列表，将事件格式化为 SSE 流输出。"""
    async with event_bus.subscribe(topics) as q:
        yield 'data: {"event":"connected"}\n\n'
        while True:
            if await request.is_disconnected():
                break
            try:
                payload: dict = await asyncio.wait_for(q.get(), timeout=_KEEPALIVE_INTERVAL)
                event_type = payload.get("event", "message")
                data = json.dumps(payload, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"


@router.head("")
async def event_stream_head(
    session: SessionData = Depends(require_auth),  # noqa: ARG001
) -> dict:
    """HEAD 预检端点：供前端 useSSE 检测可用性，不开启流。"""
    return {}


@router.get("")
async def event_stream(
    request: Request,
    session: SessionData = Depends(require_auth),
) -> StreamingResponse:
    """
    SSE 统一推送流。

    事件类型：
    - location   — GPS 定位帧（1 s/次）
    - alert      — 超速 / 越界 / 禁运告警
    - device_state — 设备上线 / 下线 / 心跳超时

    管理员订阅全量；车队用户仅接收本车队数据。
    """
    if session.fleet_id is None:
        topics = ["location:all", "alert:all", "device_state"]
    else:
        fid = session.fleet_id
        topics = [f"location:{fid}", f"alert:{fid}", "device_state"]

    return StreamingResponse(
        _sse_generator(request, topics),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
