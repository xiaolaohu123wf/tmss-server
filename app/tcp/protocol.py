from __future__ import annotations

import json
import re
from typing import Optional, Union

_IMEI_RE = re.compile(r"\b(\d{14,15})\b")
_FV_RE = re.compile(r"^\{fv:([0-9]+(?:\.[0-9]+)*)\}$")

# 协议中精简字段名 → 标准字段名
_TYPE_MAP: dict[str, str] = {"g": "gps", "b": "lbs"}


def _login_array_to_register_dict(arr: list) -> Optional[dict]:
    """DTU 常见 JSON 数组登录：["login", "<imei>", ...]。"""
    if len(arr) < 2:
        return None
    if str(arr[0]).lower() != "login":
        return None
    imei = str(arr[1]).strip()
    if not imei:
        return None
    return {
        "type": "register",
        "imei": imei,
        "_login_array_ack": True,
    }


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

    # DTU「HEX 心跳 00」常发两字节 ASCII 0x30,0x30，与单字节 NUL 等同视为心跳
    if text == "00":
        return raw

    # 固件版本上报：{fv:1.0.1}
    m = _FV_RE.match(text)
    if m:
        return {"type": "firmware_version", "version": m.group(1)}

    # 纯 ASCII 命令
    lower = text.lower()
    if lower == "rt":
        return "rt"
    if lower == "rw":
        return "rw"

    try:
        container = json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        container = None
    if isinstance(container, list):
        login_reg = _login_array_to_register_dict(container)
        if login_reg is not None:
            return login_reg
        return None
    if isinstance(container, dict):
        return _normalize(container)

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
    if not m:
        return None
    d = m.group(1)
    if len(d) == 14:
        return "0" + d
    return d


def split_frames(buf: bytes) -> tuple[list[bytes], bytes]:
    """
    分帧策略（按优先级）：
    1. 按最早出现的 \\n 或 \\r 切成行（DTU 常用 \\r 串联 rt、rw）
    2. 剩余数据再尝试 JSON / 心跳粘包解析
    """
    buf = buf.replace(b"\r\n", b"\n")
    frames: list[bytes] = []

    while True:
        idx_n = buf.find(b"\n")
        idx_r = buf.find(b"\r")
        candidates = [i for i in (idx_n, idx_r) if i != -1]
        if not candidates:
            break
        idx = min(candidates)
        frame, buf = buf[:idx], buf[idx + 1 :]
        frame = frame.strip()
        if frame:
            frames.append(frame)

    tail = buf.strip()
    if tail.lower() in (b"rt", b"rw"):
        frames.append(tail)
        return frames, b""

    if buf:
        ls = buf.lstrip()
        head1 = ls[:1]
        jsonish = head1 in (b"{", b"[") or buf.startswith(b"\x00") or (
            len(buf) >= 2
            and buf[:2] == b"00"
            and _ascii00_followed_by_json_or_end(buf, 2, len(buf))
        )
        if jsonish:
            j_frames, rest = _extract_json_objects(buf)
            frames.extend(j_frames)
            return frames, rest
        return frames, buf
    return frames, b""


def _ascii00_followed_by_json_or_end(buf: bytes, j: int, n: int) -> bool:
    """`00` 之后是否为缓冲末尾或下一个非空白字符为 JSON 起首 `{` `[`。"""
    while j < n and buf[j : j + 1] in (b" ", b"\t", b"\r"):
        j += 1
    return j >= n or buf[j : j + 1] in (b"{", b"[")


def _extract_json_objects(buf: bytes) -> tuple[list[bytes], bytes]:
    """从连续字节流中提取完整 JSON 对象（无任何分隔符时使用）。"""
    frames: list[bytes] = []
    i = 0
    n = len(buf)
    while i < n:
        # 无前导换行时，单字节 NUL / 前缀 "00" 易被下方「跳过非 JSON」逻辑吞掉，须优先成帧
        if buf[i] == 0:
            frames.append(b"\x00")
            i += 1
            continue
        if (
            i + 2 <= n
            and buf[i : i + 2] == b"00"
            and _ascii00_followed_by_json_or_end(buf, i + 2, n)
        ):
            frames.append(b"00")
            i += 2
            continue

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
