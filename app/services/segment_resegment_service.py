"""
轨迹分段批处理服务（v1.2.0）

核心类 SegmentFSM 是纯 Python 状态机，不依赖任何 I/O。
批处理入口 resegment_device() 对单台设备执行全量重分析：
  1. 删除 cutoff 之后的旧段
  2. 拉取原始 GPS 定位点（按时间正序）
  3. 预加载装/卸料围栏（内存内交叉检测）
  4. 逐点驱动 SegmentFSM
  5. 批量写入新段
  6. 更新 point_count

六种段类型说明
--------------
loading          装料中（进入装料区即刻确认）
unloading        卸料中（进入卸料区即刻确认）
transport_loaded 重载运输中（离开装料区 → 未超时到达卸料区）
transport_empty  空载中（离开卸料区 → 未超时到达装料区）
unknown          未知状态（运输超时后原地改类型；首次开机；其他无法分类情况）
idle             停车（不在装/卸区、100 m 内静止 ≥ park_threshold_min 分钟；默认隐藏）
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import asyncpg
import structlog

from app.core.enums import ZoneType
from app.db.repos.geo_zone_repo import GeoZoneRow
from app.services.geofence_service import point_in_polygon, wgs84_to_gcj02

logger = structlog.get_logger()

# 停车判定半径（米）：100 m 内持续不动达阈值 → idle
IDLE_RADIUS_M = 100.0

_TRANSPORT_TYPES = frozenset(["transport_loaded", "transport_empty"])
_WORK_ZONE_TYPES = frozenset(["loading", "unloading"])


# ---------------------------------------------------------------------------
# 辅助：Haversine 距离（米）
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(min(1.0, a)))


# ---------------------------------------------------------------------------
# 内存围栏检测（批处理中一次性加载围栏，逐点调用）
# ---------------------------------------------------------------------------

def zones_at_point_sync(
    lat_wgs: float,
    lng_wgs: float,
    loading_zones: list[GeoZoneRow],
    unloading_zones: list[GeoZoneRow],
) -> tuple[Optional[GeoZoneRow], Optional[GeoZoneRow]]:
    """返回 (loading_zone_or_None, unloading_zone_or_None)。装料区优先。"""
    lat_gcj, lng_gcj = wgs84_to_gcj02(lat_wgs, lng_wgs)
    loading_hit: Optional[GeoZoneRow] = None
    unloading_hit: Optional[GeoZoneRow] = None
    for z in loading_zones:
        if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
            loading_hit = z
            break
    for z in unloading_zones:
        if z.coordinates and point_in_polygon(lat_gcj, lng_gcj, z.coordinates):
            unloading_hit = z
            break
    return loading_hit, unloading_hit


# ---------------------------------------------------------------------------
# 段数据结构（已关闭，准备写库）
# ---------------------------------------------------------------------------

@dataclass
class SegmentRecord:
    device_id: int
    vehicle_id: Optional[int]
    started_at: datetime
    ended_at: datetime
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    segment_type: str


# ---------------------------------------------------------------------------
# 核心有限状态机（纯内存，无 I/O）
# ---------------------------------------------------------------------------

@dataclass
class SegmentFSM:
    """
    轨迹分段有限状态机。

    用法::

        fsm = SegmentFSM(device_id=42)
        for pt in points:
            loading_z, unloading_z = zones_at_point_sync(pt.lat, pt.lng, lz, uz)
            fsm.process(pt.lat, pt.lng, pt.recorded_at, pt.vehicle_id,
                        loading_z, unloading_z, cfg)
        fsm.flush()
        result = fsm.segments  # list[SegmentRecord]
    """

    device_id: int

    # 已关闭的段（最终结果）
    segments: list[SegmentRecord] = field(default_factory=list)

    # 当前开放段
    seg_type: Optional[str] = None
    seg_started_at: Optional[datetime] = None
    seg_start_lat: Optional[float] = None
    seg_start_lng: Optional[float] = None

    # 最后已知点（用于段结束坐标和 flush）
    last_lat: float = 0.0
    last_lng: float = 0.0
    last_at: Optional[datetime] = None
    last_vehicle_id: Optional[int] = None

    # 围栏驻留计时（vehicle_id 跟随当前点）
    zone_entry_id: Optional[int] = None
    zone_entry_at: Optional[datetime] = None
    zone_entry_lat: float = 0.0
    zone_entry_lng: float = 0.0

    # 运输计时
    transport_started_at: Optional[datetime] = None

    # 停车锚点（仅在围栏外启用）
    anchor_lat: Optional[float] = None
    anchor_lng: Optional[float] = None
    anchor_since: Optional[datetime] = None

    # ── 内部帮助 ──────────────────────────────────────────────────────────

    def _close(self, ended_at: datetime, end_lat: float, end_lng: float) -> None:
        """关闭当前段并追加到 segments（时长为零/负的段跳过）。"""
        if self.seg_type is not None and self.seg_started_at is not None:
            if ended_at > self.seg_started_at:
                self.segments.append(SegmentRecord(
                    device_id=self.device_id,
                    vehicle_id=self.last_vehicle_id,
                    started_at=self.seg_started_at,
                    ended_at=ended_at,
                    start_lat=self.seg_start_lat if self.seg_start_lat is not None else end_lat,
                    start_lng=self.seg_start_lng if self.seg_start_lng is not None else end_lng,
                    end_lat=end_lat,
                    end_lng=end_lng,
                    segment_type=self.seg_type,
                ))
        self.seg_type = None
        self.seg_started_at = None
        self.seg_start_lat = None
        self.seg_start_lng = None

    def _open(
        self,
        seg_type: str,
        started_at: datetime,
        lat: float,
        lng: float,
        vehicle_id: Optional[int],
    ) -> None:
        self.seg_type = seg_type
        self.seg_started_at = started_at
        self.seg_start_lat = lat
        self.seg_start_lng = lng
        self.last_vehicle_id = vehicle_id

    # ── 主驱动 ────────────────────────────────────────────────────────────

    def process(
        self,
        lat: float,
        lng: float,
        recorded_at: datetime,
        vehicle_id: Optional[int],
        loading_zone: Optional[GeoZoneRow],
        unloading_zone: Optional[GeoZoneRow],
        *,
        park_threshold_min: int,
        transport_timeout_min: int,
    ) -> None:
        # 装料区优先
        active_zone = loading_zone or unloading_zone

        # ── 初始化第一个段 ────────────────────────────────────────────────
        if self.seg_type is None:
            self._open("unknown", recorded_at, lat, lng, vehicle_id)

        # ── GPS 时间跳变检测：间隔 ≥ 停车阈值 → 强制切段 ─────────────────
        elif (
            self.last_at is not None
            and (recorded_at - self.last_at).total_seconds() / 60.0 >= park_threshold_min
        ):
            self._close(self.last_at, self.last_lat, self.last_lng)
            self._open("unknown", recorded_at, lat, lng, vehicle_id)
            self.zone_entry_id = None
            self.zone_entry_at = None
            self.transport_started_at = None
            self.anchor_lat = None
            self.anchor_lng = None
            self.anchor_since = None
            # 继续处理围栏逻辑（当前包可能已在工作区域）

        # ── 围栏区域逻辑 ──────────────────────────────────────────────────
        if active_zone:
            zone_type = "loading" if loading_zone else "unloading"

            if self.zone_entry_id != active_zone.id:
                # 进入新围栏
                self.zone_entry_id = active_zone.id
                self.zone_entry_at = recorded_at
                self.zone_entry_lat = lat
                self.zone_entry_lng = lng

            # 进入围栏立即确认装/卸料（不重复标记已确认的装/卸料段）
            if (
                self.seg_type not in _WORK_ZONE_TYPES
                and self.zone_entry_at is not None
            ):
                # 回溯：关闭前段（结束于 zone_entry_at），从 zone_entry_at 开启新段
                self._close(self.zone_entry_at, self.zone_entry_lat, self.zone_entry_lng)
                self._open(zone_type, self.zone_entry_at, self.zone_entry_lat, self.zone_entry_lng, vehicle_id)
                self.transport_started_at = None
                # 在围栏内不做 idle 检测
                self.anchor_lat = None
                self.anchor_lng = None
                self.anchor_since = None

        else:
            # 在围栏外
            if self.zone_entry_id is not None and self.seg_type in _WORK_ZONE_TYPES:
                # 已确认装/卸料段 → 关闭工作段，开启运输段，清除围栏计时
                prev = self.seg_type
                self._close(recorded_at, lat, lng)
                next_type = "transport_loaded" if prev == "loading" else "transport_empty"
                self._open(next_type, recorded_at, lat, lng, vehicle_id)
                self.transport_started_at = recorded_at
                self.zone_entry_id = None
                self.zone_entry_at = None
            # 未确认驻留的短暂离开：保留 zone_entry_ 不清除，防止 GPS 边界抖动使计时重置

            # ── 运输超时检测 ──────────────────────────────────────────────
            if (
                self.seg_type in _TRANSPORT_TYPES
                and self.transport_started_at is not None
                and transport_timeout_min > 0
                and (recorded_at - self.transport_started_at).total_seconds() / 60.0
                >= transport_timeout_min
            ):
                # 原地改类型为 unknown（方案 X：不拆段）
                self.seg_type = "unknown"
                self.transport_started_at = None

            # ── 停车 / idle 检测（仅在围栏外）────────────────────────────
            if self.anchor_lat is None:
                self.anchor_lat = lat
                self.anchor_lng = lng
                self.anchor_since = recorded_at
            else:
                dist = _haversine_m(self.anchor_lat, self.anchor_lng, lat, lng)
                if dist > IDLE_RADIUS_M:
                    # 车辆移动：重置锚点
                    if self.seg_type == "idle":
                        # 离开停车状态 → 开启 unknown
                        self._close(recorded_at, lat, lng)
                        self._open("unknown", recorded_at, lat, lng, vehicle_id)
                    self.anchor_lat = lat
                    self.anchor_lng = lng
                    self.anchor_since = recorded_at
                else:
                    # 仍在停车范围内
                    if (
                        self.seg_type != "idle"
                        and self.anchor_since is not None
                        and (recorded_at - self.anchor_since).total_seconds() / 60.0
                        >= park_threshold_min
                    ):
                        # 停车阈值到达 → 回溯关闭，从 anchor_since 开启 idle
                        self._close(self.anchor_since, lat, lng)
                        self._open("idle", self.anchor_since, lat, lng, vehicle_id)

        # ── 更新最后已知点 ────────────────────────────────────────────────
        self.last_lat = lat
        self.last_lng = lng
        self.last_at = recorded_at
        self.last_vehicle_id = vehicle_id

    def flush(self) -> None:
        """关闭最后一个开放段（处理完全部点后调用一次）。"""
        if self.seg_type is not None and self.seg_started_at is not None and self.last_at is not None:
            self._close(self.last_at, self.last_lat, self.last_lng)


# ---------------------------------------------------------------------------
# 批处理入口：对单台设备执行全量重分析
# ---------------------------------------------------------------------------

async def resegment_device(
    device_id: int,
    cutoff: datetime,
    conn: asyncpg.Connection,  # type: ignore[type-arg]
    park_threshold_min: int,
    transport_timeout_min: int,
    loading_zones: list[GeoZoneRow],
    unloading_zones: list[GeoZoneRow],
) -> int:
    """
    对单台设备执行全量重分析。返回创建的段数量。

    步骤：
    1. 删除该设备在 cutoff 之后的所有旧段
    2. 拉取原始 GPS 定位点（按时间正序）
    3. 驱动 SegmentFSM
    4. 批量 INSERT 新段（point_count=0）
    5. UPDATE point_count（时间范围匹配）
    """
    # 1. 清除旧段
    await conn.execute(
        "DELETE FROM track_segment WHERE device_id = $1 AND started_at >= $2",
        device_id,
        cutoff,
    )

    # 2. 读取 GPS 点（过滤 LBS）
    rows = await conn.fetch(
        """
        SELECT vehicle_id,
               recorded_at,
               lat::DOUBLE PRECISION AS lat,
               lng::DOUBLE PRECISION AS lng
        FROM location_point
        WHERE device_id   = $1
          AND recorded_at >= $2
          AND loc_type    = 'gps'
        ORDER BY recorded_at ASC, id ASC
        """,
        device_id,
        cutoff,
    )
    if not rows:
        return 0

    # 3. 驱动状态机
    fsm = SegmentFSM(device_id=device_id)
    for row in rows:
        lat = float(row["lat"])
        lng = float(row["lng"])
        lz, uz = zones_at_point_sync(lat, lng, loading_zones, unloading_zones)
        fsm.process(
            lat=lat,
            lng=lng,
            recorded_at=row["recorded_at"],
            vehicle_id=row["vehicle_id"],
            loading_zone=lz,
            unloading_zone=uz,
            park_threshold_min=park_threshold_min,
            transport_timeout_min=transport_timeout_min,
        )
    fsm.flush()

    if not fsm.segments:
        return 0

    # 4. 批量 INSERT
    records = [
        (
            s.device_id,
            s.vehicle_id,
            s.started_at,
            s.ended_at,
            s.start_lat,
            s.start_lng,
            s.end_lat,
            s.end_lng,
            s.segment_type,
            0,   # point_count 先填 0，后续 UPDATE
        )
        for s in fsm.segments
    ]
    await conn.copy_records_to_table(
        "track_segment",
        records=records,
        columns=[
            "device_id", "vehicle_id", "started_at", "ended_at",
            "start_lat", "start_lng", "end_lat", "end_lng",
            "segment_type", "point_count",
        ],
    )

    # 5. UPDATE point_count（按时间范围精确匹配定位点）
    await conn.execute(
        """
        UPDATE track_segment ts
        SET point_count = (
            SELECT COUNT(*)
            FROM location_point lp
            WHERE lp.device_id   = ts.device_id
              AND lp.recorded_at >= ts.started_at
              AND lp.recorded_at <= ts.ended_at
              AND lp.loc_type    = 'gps'
        )
        WHERE ts.device_id   = $1
          AND ts.started_at >= $2
        """,
        device_id,
        cutoff,
    )

    return len(fsm.segments)
