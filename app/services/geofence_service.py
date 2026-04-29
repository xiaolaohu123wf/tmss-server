"""
坐标转换与围栏服务。

WGS-84 → GCJ-02 转换：设备上报 WGS-84，围栏存储与空间判定使用 GCJ-02。
围栏列表在进程内缓存（默认 5 分钟刷新），避免每包都查数据库。
"""
from __future__ import annotations

import asyncio
import math
import time as _time
from dataclasses import dataclass
from typing import Optional

import asyncpg
import structlog

from app.core.enums import ZoneType
from app.db.repos.geo_zone_repo import GeoZoneRepo, GeoZoneRow

logger = structlog.get_logger()

_ZONE_CACHE_TTL = 300.0  # 5 分钟
_PI = math.pi
_EE = 0.00669342162296594323  # 扁率参数

_geo_zone_repo = GeoZoneRepo()


# ---------------------------------------------------------------------------
# WGS-84 → GCJ-02 转换（国测局坐标/火星坐标）
# ---------------------------------------------------------------------------

def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * _PI) + 40.0 * math.sin(y / 3.0 * _PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * _PI) + 320 * math.sin(y * _PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lng(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * _PI) + 20.0 * math.sin(2.0 * x * _PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * _PI) + 40.0 * math.sin(x / 3.0 * _PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * _PI) + 300.0 * math.sin(x / 30.0 * _PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat: float, lng: float) -> tuple[float, float]:
    """WGS-84 → GCJ-02（国内坐标，火星坐标系）。"""
    d_lat = _transform_lat(lng - 105.0, lat - 35.0)
    d_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * _PI
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((6378245.0 * (1 - _EE)) / (magic * sqrt_magic) * _PI)
    d_lng = (d_lng * 180.0) / (6378245.0 / sqrt_magic * math.cos(rad_lat) * _PI)
    return lat + d_lat, lng + d_lng


# ---------------------------------------------------------------------------
# 射线法：点是否在多边形内
# coords: [[lng, lat], ...]  (GeoJSON 顺序)
# ---------------------------------------------------------------------------

def point_in_polygon(lat: float, lng: float, coords: list[list[float]]) -> bool:
    """射线法判断点 (lat, lng) 是否在多边形内。coords 格式为 [[lng, lat], ...]。"""
    n = len(coords)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = coords[i][0], coords[i][1]   # lng, lat
        xj, yj = coords[j][0], coords[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# 区域缓存
# ---------------------------------------------------------------------------

@dataclass
class _ZoneCache:
    zones: list[GeoZoneRow]
    loaded_at: float


_cache: Optional[_ZoneCache] = None
_cache_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


async def _load_zones(conn: asyncpg.Connection) -> list[GeoZoneRow]:  # type: ignore[type-arg]
    global _cache
    async with _get_lock():
        now = _time.monotonic()
        if _cache is None or now - _cache.loaded_at > _ZONE_CACHE_TTL:
            zones = await _geo_zone_repo.find_all_enabled(conn)
            _cache = _ZoneCache(zones=zones, loaded_at=now)
            await logger.ainfo("geo_zone_cache_refreshed", count=len(zones))
    return _cache.zones


def invalidate_zone_cache() -> None:
    """手动失效缓存（围栏数据发生变更后调用）。"""
    global _cache
    _cache = None


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

async def get_zones_at(
    lat_wgs: float,
    lng_wgs: float,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
) -> list[GeoZoneRow]:
    """返回包含 WGS-84 点位的所有启用围栏（内部转换为 GCJ-02 再判定）。"""
    lat_gcj, lng_gcj = wgs84_to_gcj02(lat_wgs, lng_wgs)
    zones = await _load_zones(conn)
    result: list[GeoZoneRow] = []
    for z in zones:
        if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
            result.append(z)
    return result


def get_zone_speed_limit(zones: list[GeoZoneRow], global_limit: int) -> tuple[int, Optional[int]]:
    """
    返回 (有效限速, 命中的 zone_id)。
    优先使用有 speed_limit 的 SPEED_ZONE，其次全局限速。
    """
    for z in zones:
        if z.zone_type == ZoneType.SPEED_ZONE and z.speed_limit is not None:
            return z.speed_limit, z.id
    return global_limit, None
