"""TCP 原始收发调试：环形缓冲 + 可选 stdout 打印。供 HTTP /api/admin/tcp-messages 拉取。"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import settings

_MAX_ENTRIES = 2000
_MAX_STORE_BYTES = 4096


@dataclass(frozen=True)
class RawTraceRecord:
    ts_iso: str
    direction: str  # "rx" | "tx"
    peer: str
    length: int
    hex: str
    truncated: bool


_lock = threading.Lock()
_buffer: deque[RawTraceRecord] = deque(maxlen=_MAX_ENTRIES)


def peer_from_writer(writer: asyncio.StreamWriter) -> str:
    peer = writer.get_extra_info("peername")
    if peer and len(peer) >= 2:
        return f"{peer[0]}:{peer[1]}"
    return "unknown"


def _hex_snippet(data: bytes) -> tuple[str, bool]:
    if len(data) <= _MAX_STORE_BYTES:
        return (data.hex(), False)
    return (data[:_MAX_STORE_BYTES].hex(), True)


def record_rx(peer: str, data: bytes) -> None:
    _record("rx", peer, data)


def record_tx(writer: asyncio.StreamWriter, data: bytes) -> None:
    _record("tx", peer_from_writer(writer), data)


def record_tx_peer(peer: str, data: bytes) -> None:
    """设备下行等场景已知 peer 时使用。"""
    _record("tx", peer, data)


def _record(direction: str, peer: str, data: bytes) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    hx, trunc = _hex_snippet(data)
    rec = RawTraceRecord(
        ts_iso=ts,
        direction=direction,
        peer=peer,
        length=len(data),
        hex=hx,
        truncated=trunc,
    )
    with _lock:
        _buffer.append(rec)
    if settings.tcp_raw_print:
        print(
            f"[TCP {direction.upper()}] {ts} {peer} len={len(data)}"
            f"{'+' if trunc else ''} hex={hx}{'...' if trunc else ''}",
            flush=True,
        )


def snapshot_tail(limit: int = 500) -> list[RawTraceRecord]:
    lim = max(1, min(limit, _MAX_ENTRIES))
    with _lock:
        items = list(_buffer)
    return items[-lim:] if len(items) > lim else items


def bytes_to_printable_ascii(data: bytes) -> str:
    """可打印 ASCII（32–126）原样输出，制表符等转义，其余为 \\xHH。"""
    parts: list[str] = []
    for b in data:
        if 32 <= b <= 126:
            parts.append(chr(b))
        elif b == 9:
            parts.append("\\t")
        elif b == 10:
            parts.append("\\n")
        elif b == 13:
            parts.append("\\r")
        else:
            parts.append(f"\\x{b:02x}")
    return "".join(parts)


def record_payload_ascii(record: RawTraceRecord) -> str:
    """由缓冲中的 hex 片段还原为 ASCII 可读串（截断记录会标注）。"""
    try:
        raw = bytes.fromhex(record.hex)
    except ValueError:
        return ""
    if not record.truncated:
        if raw == b"\x00":
            return "<HEARTBEAT 0x00>"
        if raw == b"00":
            return "<HEARTBEAT ASCII '00' (0x3030)>"
    text = bytes_to_printable_ascii(raw)
    if record.truncated:
        return f"{text}...(truncated, stored_prefix_len={len(raw)}, total_len={record.length})"
    return text


def clear() -> None:
    with _lock:
        _buffer.clear()
