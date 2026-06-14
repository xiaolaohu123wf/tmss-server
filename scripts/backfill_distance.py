"""一次性回填 track_segment.distance_km（V011 迁移后执行）。

逐条计算，每条 UPDATE 独立提交：单段扫描点数有限（通常 100-3600 点），
单条耗时 1-20ms，避免大 CTE 一次扫描数百万行导致超时或 OOM。

用法：
  source .venv/bin/activate
  DATABASE_URL=postgresql://... python scripts/backfill_distance.py
"""
import asyncio
import os
import time

import asyncpg

FETCH_NULL_SQL = """
    SELECT id
    FROM track_segment
    WHERE ended_at IS NOT NULL AND distance_km IS NULL
    ORDER BY ended_at DESC
    LIMIT 500
"""

COMPUTE_ONE_SQL = """
    WITH ordered AS (
        SELECT
            lp.lat::DOUBLE PRECISION  AS lat,
            lp.lng::DOUBLE PRECISION  AS lng,
            LAG(lp.lat::DOUBLE PRECISION)
                OVER (ORDER BY lp.recorded_at, lp.id) AS prev_lat,
            LAG(lp.lng::DOUBLE PRECISION)
                OVER (ORDER BY lp.recorded_at, lp.id) AS prev_lng
        FROM track_segment ts
        JOIN location_point lp
             ON  lp.device_id   = ts.device_id
             AND lp.recorded_at >= ts.started_at
             AND lp.recorded_at <= ts.ended_at
             AND lp.loc_type    = 'gps'
        WHERE ts.id = $1
    )
    UPDATE track_segment
    SET distance_km = (
        SELECT COALESCE(SUM(
            CASE WHEN prev_lat IS NULL THEN 0.0
            ELSE 6371.0088 * ACOS(LEAST(1.0, GREATEST(-1.0,
                SIN(RADIANS(prev_lat)) * SIN(RADIANS(lat))
                + COS(RADIANS(prev_lat)) * COS(RADIANS(lat))
                  * COS(RADIANS(lng - prev_lng))
            ))) END
        ), 0.0)
        FROM ordered
    )
    WHERE id = $1
      AND ended_at IS NOT NULL
"""


async def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("请设置环境变量 DATABASE_URL")
    conn = await asyncpg.connect(db_url)
    done = 0
    t0 = time.perf_counter()
    while True:
        ids = [r["id"] for r in await conn.fetch(FETCH_NULL_SQL)]
        if not ids:
            break
        for seg_id in ids:
            t1 = time.perf_counter()
            await conn.execute(COMPUTE_ONE_SQL, seg_id)
            ms = (time.perf_counter() - t1) * 1000
            done += 1
            if done % 50 == 0:
                print(f"  {done} done ... last={ms:.0f}ms")
        print(f"batch complete: {done} so far ({time.perf_counter()-t0:.1f}s elapsed)")

    print(f"\nAll done. {done} segments in {time.perf_counter()-t0:.1f}s")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
