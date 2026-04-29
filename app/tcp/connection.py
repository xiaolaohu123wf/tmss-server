from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from app.core.device_registry import device_registry
from app.db.pool import get_pool
from app.tcp.handlers.heartbeat_handler import HeartbeatHandler
from app.tcp.handlers.register_handler import RegisterHandler
from app.tcp.handlers.time_weather_handler import TimeWeatherHandler
from app.tcp.protocol import extract_imei, parse_frame, split_frames

logger = structlog.get_logger()

MAX_BUF = 64 * 1024  # 64 KB 防内存爆炸

_register_handler = RegisterHandler(device_registry)
_heartbeat_handler = HeartbeatHandler(device_registry)
_time_weather_handler = TimeWeatherHandler()


class ConnectionHandler:
    """单条 TCP 连接的完整生命周期管理。"""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._device_id: Optional[int] = None
        self._imei: Optional[str] = None
        peer = writer.get_extra_info("peername")
        self._peer = f"{peer[0]}:{peer[1]}" if peer else "unknown"

    async def run(self) -> None:
        await logger.ainfo("tcp_connected", peer=self._peer)
        buf = b""
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(self._reader.read(4096), timeout=120)
                except asyncio.TimeoutError:
                    await logger.awarning("tcp_read_timeout", peer=self._peer)
                    break
                if not chunk:
                    break  # 对端关闭

                buf += chunk
                if len(buf) > MAX_BUF:
                    await logger.awarning("tcp_buf_overflow", peer=self._peer)
                    break

                frames, buf = split_frames(buf)
                for raw in frames:
                    await self._dispatch(raw)

        except Exception as exc:
            await logger.aerror("tcp_connection_error", peer=self._peer, error=str(exc))
        finally:
            await self._cleanup()

    async def _dispatch(self, raw: bytes) -> None:
        parsed = parse_frame(raw)
        if parsed is None:
            return

        # 心跳包
        if isinstance(parsed, bytes):
            if self._device_id is not None:
                await _heartbeat_handler.handle(self._device_id)
            return

        # 时间/天气请求
        if parsed == "rt":
            await _time_weather_handler.handle_time(self._writer)
            return
        if parsed == "rw":
            await _time_weather_handler.handle_weather(self._writer)
            return

        # JSON 对象
        if not isinstance(parsed, dict):
            return

        msg_type = parsed.get("type", "")

        # 注册包
        if msg_type == "register" or "deviceId" in parsed or (
            "imei" not in parsed and self._device_id is None and extract_imei(raw)
        ):
            await self._handle_register(parsed, raw)
            return

        # GPS 定位包（高频简包）
        if msg_type in ("gps", "lbs") and "lat" in parsed:
            await self._handle_gps(parsed)
            return

        # 全量状态包（含 imei 字段）
        if "imei" in parsed:
            await self._handle_full_state(parsed)
            return

    async def _handle_register(self, obj: dict, raw: bytes) -> None:
        imei = (
            obj.get("imei")
            or obj.get("deviceId")
            or obj.get("device_id")
            or extract_imei(raw)
        )
        if not imei:
            await logger.awarning("register_no_imei", peer=self._peer)
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            device_id = await _register_handler.handle(imei, self._writer, conn)

        if device_id:
            self._device_id = device_id
            self._imei = imei
            await logger.ainfo("device_online", device_id=device_id, imei=imei, peer=self._peer)

    async def _handle_gps(self, obj: dict) -> None:
        if self._device_id is None:
            return
        from app.models.tcp_packets import GpsPacket
        try:
            packet = GpsPacket(
                lat=float(obj["lat"]),
                lng=float(obj["lng"]),
                speed=float(obj["speed"]) if obj.get("speed") is not None else None,
                altitude=float(obj["altitude"]) if obj.get("altitude") is not None else None,
            )
        except (KeyError, ValueError, TypeError):
            return
        await device_registry.push_point(self._device_id, packet)
        # 阶段 6 会在此调用 LocationRepo.insert 和 AlertService

    async def _handle_full_state(self, obj: dict) -> None:
        if self._device_id is None:
            return
        # 阶段 6 will handle firmware/ICCID updates here
        pass

    async def _cleanup(self) -> None:
        if self._device_id is not None:
            await device_registry.unregister(self._device_id)
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass
        await logger.ainfo("tcp_disconnected", peer=self._peer, device_id=self._device_id)
