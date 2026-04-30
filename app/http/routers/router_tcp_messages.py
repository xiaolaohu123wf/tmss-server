"""管理员查看 TCP 原始收发缓冲（仅排错）。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from app.http.deps import require_tcp_debug_access
from app.http.response import ok
from app.tcp.raw_trace import clear, record_payload_ascii, snapshot_tail

router = APIRouter(
    prefix="/api/admin",
    tags=["tcp-debug"],
    dependencies=[Depends(require_tcp_debug_access)],
)


@router.get(
    "/tcp-messages",
    response_model=None,
    summary="最近 TCP 原始收发（环形缓冲）",
)
async def get_tcp_messages(
    limit: int = Query(500, ge=1, le=2000),
    fmt: Literal["blocks", "json", "text"] = Query(
        "blocks",
        alias="format",
        description="blocks=多行块（默认）| json | text=单行制表",
    ),
    refresh: int = Query(
        5,
        ge=0,
        le=86400,
        description="浏览器自动刷新秒数，0 表示不设 Refresh 头（适合 curl）",
    ),
):
    rows = snapshot_tail(limit)
    if fmt == "json":
        payload = [
            {
                "ts": r.ts_iso,
                "direction": r.direction,
                "peer": r.peer,
                "length": r.length,
                "truncated": r.truncated,
                "segment": r.segment,
                "ascii": record_payload_ascii(r),
                "hex": r.hex,
            }
            for r in rows
        ]
        body = ok(payload)
        response: JSONResponse = JSONResponse(content=body)
        if refresh > 0:
            response.headers["Refresh"] = str(refresh)
        return response
    if fmt == "blocks":
        parts: list[str] = []
        for r in rows:
            kind = "接收" if r.direction == "rx" else "发送"
            frame_tag = " [逻辑帧]" if r.segment == "frame" else ""
            line1 = (
                f"{kind}{frame_tag} | {r.peer} | {r.ts_iso} | len={r.length}"
                f"{' (truncated)' if r.truncated else ''}"
            )
            line2 = record_payload_ascii(r)
            parts.extend([line1, line2, ""])
        body = "\n".join(parts)
        out = PlainTextResponse(
            body,
            media_type="text/plain; charset=utf-8",
        )
        if refresh > 0:
            out.headers["Refresh"] = str(refresh)
        return out
    body_lines: list[str] = []
    for r in rows:
        flag = "+" if r.truncated else ""
        seg = "[帧]" if r.segment == "frame" else ""
        body_lines.append(
            f"{r.ts_iso}\t{r.direction}\t{seg}\t{r.peer}\tlen={r.length}{flag}\t"
            f"{record_payload_ascii(r)}",
        )
    text_res = PlainTextResponse(
        "\n".join(body_lines) + ("\n" if body_lines else ""),
        media_type="text/plain; charset=utf-8",
    )
    if refresh > 0:
        text_res.headers["Refresh"] = str(refresh)
    return text_res


@router.delete("/tcp-messages", summary="清空 TCP 收发缓冲")
async def delete_tcp_messages() -> dict:
    clear()
    return ok({"cleared": True})
