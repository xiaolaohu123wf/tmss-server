from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from app.core.device_registry import device_registry
from app.core.event_bus import event_bus
from app.db.pool import get_pool
from app.db.queries.business_config import SELECT_BUSINESS_CONFIG_SQL
from app.core.enums import ZoneType
from app.db.repos.geo_zone_repo import GeoZoneRepo
from app.tcp.handlers.heartbeat_handler import HeartbeatHandler
from app.tcp.handlers.register_handler import RegisterHandler
from app.tcp.handlers.time_weather_handler import TimeWeatherHandler
from app.tcp.handlers.gps_handler import GpsHandler
from app.tcp.handlers.full_state_handler import FullStateHandler
from app.tcp.protocol import extract_imei, parse_frame, split_frames
from app.models.tcp_packets import FullStatePacket

logger = structlog.get_logger()

MAX_BUF = 64 * 1024  # 64 KB 防内存爆炸

_register_handler = RegisterHandler(device_registry)
_heartbeat_handler = HeartbeatHandler(device_registry)
_time_weather_handler = TimeWeatherHandler()
_full_state_handler = FullStateHandler(device_registry)
_gps_handler: Optional[GpsHandler] = None
_geo_zone_repo = GeoZoneRepo()


async def _get_gps_handler() -> GpsHandler:
    """懒加载：首次使用时从 DB 读取业务配置，之后复用同一实例。"""
    global _gps_handler
    if _gps_handler is not None:
        return _gps_handler

    pool = await get_pool()
    async with pool.acquire() as conn:
        cfg = await conn.fetchrow(SELECT_BUSINESS_CONFIG_SQL)
        # 判断是否存在限行围栏
        all_zones = await _geo_zone_repo.find_all_enabled(conn)
        has_restricted = any(z.zone_type == ZoneType.RESTRICTED for z in all_zones)

    if cfg:
        _gps_handler = GpsHandler(
            registry=device_registry,
            global_speed_limit=int(cfg["global_speed_limit"]),
            park_threshold_min=int(cfg["park_threshold_min"]),
            loading_dwell_min=int(cfg["loading_dwell_min"]),
            unloading_dwell_min=int(cfg["unloading_dwell_min"]),
            alert_cooldown_s=int(cfg["alert_cooldown_s"]),
            has_restricted_zones=has_restricted,
        )
    else:
        _gps_handler = GpsHandler(registry=device_registry, has_restricted_zones=has_restricted)

    await logger.ainfo("gps_handler_initialized", has_restricted=has_restricted)
    return _gps_handler


def invalidate_gps_handler() -> None:
    """围栏或业务配置变更后调用，下次 GPS 包时重新加载配置。"""
    global _gps_handler
    _gps_handler = None


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

                await logger.adebug(
                    "tcp_chunk_recv",
                    peer=self._peer,
                    length=len(chunk),
                    preview=chunk[:200],
                )

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
            await logger.adebug("frame_unparseable", peer=self._peer, raw=raw[:120])
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

        await logger.adebug("frame_received", peer=self._peer, device_id=self._device_id, keys=list(parsed.keys()))

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

        state = await device_registry.get(self._device_id)
        if state is None:
            return

        handler = await _get_gps_handler()
        try:
            await handler.handle(state, packet)
        except Exception as exc:
            await logger.aerror("gps_handler_error", device_id=self._device_id, error=str(exc))

    async def _handle_full_state(self, obj: dict) -> None:
        # 若设备尚未注册，从 imei 字段自动触发注册流程
        if self._device_id is None:
            imei = obj.get("imei") or obj.get("deviceId")
            if imei:
                await logger.ainfo("auto_register_from_full_state", imei=imei, peer=self._peer)
                await self._handle_register({"imei": imei}, str(imei).encode())
            if self._device_id is None:
                return

        state = await device_registry.get(self._device_id)
        if state is None:
            return

        try:
            await _full_state_handler.handle(state, FullStatePacket.model_validate(obj))
        except Exception as exc:
            await logger.aerror("full_state_handler_error", device_id=self._device_id, error=str(exc))

    async def _cleanup(self) -> None:
        if self._device_id is not None:
            await event_bus.publish("device_state", {
                "event": "device_state",
                "type": "disconnected",
                "device_id": self._device_id,
                "imei": self._imei or "",
            })
            await device_registry.unregister(self._device_id)
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass
        await logger.ainfo("tcp_disconnected", peer=self._peer, device_id=self._device_id)
