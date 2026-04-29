from __future__ import annotations

import json
import re
from typing import Optional, Union

_IMEI_RE = re.compile(r"\b(\d{15})\b")

# 协议中精简字段名 → 标准字段名
_TYPE_MAP: dict[str, str] = {"g": "gps", "b": "lbs"}


def parse_frame(raw: bytes) -> Optional[Union[str, dict, bytes]]:
    """
    解析单帧数据，返回以下之一：
    - bytes  : 心跳包（全零字节）
    - "rt"   : 时间查询
    - "rw"   : 天气查询
    - dict   : 已解析的 JSON 对象（register / gps / full_state 等）
    - None   : 无法识别，丢弃
    """
    if not raw:
        return None

    # 心跳包（全 0x00 字节）
    if all(b == 0 for b in raw):
        return raw

    try:
        text = raw.decode("utf-8", errors="ignore").strip()
    except Exception:
        return None

    if not text:
        return None

    # 纯 ASCII 命令
    lower = text.lower()
    if lower == "rt":
        return "rt"
    if lower == "rw":
        return "rw"

    # JSON 报文
    try:
        obj: dict = json.loads(text)
        return _normalize(obj)
    except (json.JSONDecodeError, ValueError):
        pass

    return None


def _normalize(obj: dict) -> dict:
    """统一新旧字段名（精简包 t/la/ln/sp/al → type/lat/lng/speed/altitude）。"""
    if "type" not in obj and "t" in obj:
        obj["type"] = _TYPE_MAP.get(str(obj.pop("t")), str(obj.pop("t", "")))
    if "lat" not in obj and "la" in obj:
        obj["lat"] = obj.pop("la")
    if "lng" not in obj and "ln" in obj:
        obj["lng"] = obj.pop("ln")
    if "speed" not in obj and "sp" in obj:
        sp = obj.pop("sp")
        # 如果单位是节，转 km/h；若已是 km/h（speed_kph 字段）保留
        obj["speed"] = round(float(sp) * 1.852, 2)
    if "altitude" not in obj and "al" in obj:
        obj["altitude"] = obj.pop("al")
    return obj


def extract_imei(raw: bytes) -> Optional[str]:
    """从任意报文中用正则提取 15 位 IMEI（兜底恢复身份）。"""
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return None
    m = _IMEI_RE.search(text)
    return m.group(1) if m else None


def split_frames(buf: bytes) -> tuple[list[bytes], bytes]:
    """
    分帧策略（按优先级）：
    1. 有 \\n 分隔符 → 按行切割（标准模式）
    2. 无 \\n → 用括号计数法提取完整 JSON 对象（设备直发模式）
    返回 (已完整帧列表, 剩余不完整数据)。
    """
    buf = buf.replace(b"\r\n", b"\n")

    if b"\n" in buf:
        frames: list[bytes] = []
        while b"\n" in buf:
            frame, buf = buf.split(b"\n", 1)
            frame = frame.strip()
            if frame:
                frames.append(frame)
        return frames, buf

    # 无换行符：用括号计数逐个提取 JSON 对象
    return _extract_json_objects(buf)


def _extract_json_objects(buf: bytes) -> tuple[list[bytes], bytes]:
    """从连续字节流中提取完整 JSON 对象（无任何分隔符时使用）。"""
    frames: list[bytes] = []
    i = 0
    n = len(buf)
    while i < n:
        # 跳过非 JSON 字符（空格、逗号等）
        while i < n and buf[i:i+1] not in (b"{", b"["):
            i += 1
        if i >= n:
            break
        open_char = buf[i:i+1]
        close_char = b"}" if open_char == b"{" else b"]"
        depth = 0
        in_string = False
        escape = False
        end = -1
        for j in range(i, n):
            c = buf[j:j+1]
            if escape:
                escape = False
                continue
            if c == b"\\":
                escape = True
                continue
            if c == b'"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == open_char:
                depth += 1
            elif c == close_char:
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end == -1:
            break  # 不完整，等待更多数据
        frame = buf[i:end+1].strip()
        if frame:
            frames.append(frame)
        i = end + 1
    return frames, buf[i:]
