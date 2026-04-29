from __future__ import annotations

from typing import Any


def ok(data: Any = None) -> dict[str, Any]:
    """统一成功响应格式：{"ok": true, "data": ...}"""
    return {"ok": True, "data": data}
