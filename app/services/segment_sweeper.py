"""
轨迹段后台扫描器。

每隔 SWEEP_INTERVAL_S 秒扫描一次 track_segment 表，
将所有「最后一个点已超过 park_threshold_min 分钟」的开放段关闭。

补充 connection.py 中「设备断线即关段」逻辑的安全网：
- 服务重启后内存状态丢失时；
- TCP 连接异常未触发 cleanup 时；
- 设备只发 LBS/全量包、未触发 GPS 分段逻辑时。
"""
from __future__ import annotations

import asyncio

import structlog

from app.db.pool import get_pool
from app.db.queries.business_config import SELECT_BUSINESS_CONFIG_SQL

logger = structlog.get_logger()

SWEEP_INTERVAL_S = 300   # 每 5 分钟扫一次

# 查找「最后定位点超时」的开放段（LATERAL JOIN 取最新点）
_STALE_SEGMENTS_SQL = """
    SELECT ts.id,
           lp.lat         AS end_lat,
           lp.lng         AS end_lng,
           lp.recorded_at AS ended_at
    FROM track_segment ts
    JOIN LATERAL (
        SELECT lat, lng, recorded_at
        FROM location_point
        WHERE segment_id = ts.id
        ORDER BY recorded_at DESC
        LIMIT 1
    ) lp ON true
    WHERE ts.ended_at IS NULL
      AND lp.recorded_at < NOW() - ($1 * INTERVAL '1 minute')
"""

_CLOSE_SEGMENT_SQL = """
    UPDATE track_segment
    SET ended_at = $2,
        end_lat  = $3,
        end_lng  = $4
    WHERE id = $1
      AND ended_at IS NULL
"""


async def close_stale_segments_once() -> int:
    """扫描并关闭超时开放段，返回本次关闭数量。"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        cfg = await conn.fetchrow(SELECT_BUSINESS_CONFIG_SQL)
        park_min: float = float(cfg["park_threshold_min"]) if cfg else 10.0

        rows = await conn.fetch(_STALE_SEGMENTS_SQL, park_min)
        if not rows:
            return 0

        closed = 0
        for row in rows:
            await conn.execute(
                _CLOSE_SEGMENT_SQL,
                row["id"],
                row["ended_at"],
                float(row["end_lat"]),
                float(row["end_lng"]),
            )
            closed += 1

        await logger.ainfo("stale_segments_swept", count=closed, park_threshold_min=park_min)
        return closed


async def segment_sweeper_loop() -> None:
    """后台永续协程：定期扫描超时轨迹段。"""
    await logger.ainfo("segment_sweeper_started", interval_s=SWEEP_INTERVAL_S)
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_S)
        try:
            await close_stale_segments_once()
        except Exception as exc:
            await logger.aerror("segment_sweeper_error", error=str(exc))
