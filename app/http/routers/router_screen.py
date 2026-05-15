from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.cache.session_repo import SessionData
from app.core.enums import UserRole
from app.db.deps import get_db_conn
from app.http.deps import require_fleet_or_above
from app.http.response import ok

router = APIRouter(prefix="/api/screen", tags=["screen"])

# 大屏：terminal 角色不可访问，复用 require_fleet_or_above（已包含 fleet_captain+manager）


def _fleet_id(session: SessionData) -> Optional[int]:
    return None if session.role == UserRole.MANAGER else session.fleet_id


def _parse_range(from_date: Optional[str], to_date: Optional[str]) -> Tuple[datetime, datetime]:
    """Parse YYYY-MM-DD strings into UTC datetimes. Defaults to last 30 days."""
    now = datetime.now(tz=timezone.utc)
    if from_date:
        since = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        since = now - timedelta(days=30)
    if to_date:
        until = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    else:
        until = now + timedelta(days=1)
    return since, until


# ─────────────────────────────────────────────────────────────────────────────
# 1. 概要统计
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """车辆/车队/用户数量，在线车辆数（近10分钟有定位点）"""
    fid = _fleet_id(session)

    if fid is None:
        vehicle_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vehicle WHERE deleted_at IS NULL"
        )
        fleet_count = await conn.fetchval(
            "SELECT COUNT(*) FROM fleet WHERE deleted_at IS NULL"
        )
        user_count = await conn.fetchval(
            "SELECT COUNT(*) FROM app_user WHERE deleted_at IS NULL"
        )
        online_count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT vehicle_id)
            FROM location_point
            WHERE recorded_at > NOW() - INTERVAL '10 minutes'
              AND vehicle_id IS NOT NULL
            """
        )
    else:
        vehicle_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vehicle WHERE deleted_at IS NULL AND fleet_id = $1",
            fid,
        )
        fleet_count = 1
        user_count = await conn.fetchval(
            "SELECT COUNT(*) FROM app_user WHERE deleted_at IS NULL AND fleet_id = $1",
            fid,
        )
        online_count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT lp.vehicle_id)
            FROM location_point lp
            JOIN vehicle v ON v.id = lp.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $1
            WHERE lp.recorded_at > NOW() - INTERVAL '10 minutes'
              AND lp.vehicle_id IS NOT NULL
            """,
            fid,
        )

    return ok({
        "vehicle_count": int(vehicle_count or 0),
        "fleet_count": int(fleet_count or 0),
        "user_count": int(user_count or 0),
        "online_count": int(online_count or 0),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. 轨迹段统计（里程 + 趟次）
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/segment-stats")
async def get_segment_stats(
    from_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD，默认近30天"),
    to_date: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD（含当天）"),
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """运输里程（按5种状态分组，直线×1.2修正）+ 每日运输往返趟次（可指定日期范围）"""
    fid = _fleet_id(session)
    since, until = _parse_range(from_date, to_date)

    _seg_select = """
            SELECT
              ts.segment_type,
              COALESCE(SUM(
                CASE
                  WHEN ts.start_lat IS NOT NULL AND ts.end_lat IS NOT NULL
                  THEN 2 * 6371 * asin(sqrt(
                    power(sin(radians((ts.end_lat - ts.start_lat) / 2)), 2) +
                    cos(radians(ts.start_lat)) * cos(radians(ts.end_lat)) *
                    power(sin(radians((ts.end_lng - ts.start_lng) / 2)), 2)
                  )) * 1.2
                  ELSE 0
                END
              ), 0) AS total_km,
              COALESCE(SUM(
                EXTRACT(EPOCH FROM (ts.ended_at - ts.started_at)) / 60
              ), 0) AS total_min,
              COUNT(*) AS cnt
            FROM track_segment ts
    """

    if fid is None:
        mileage_rows = await conn.fetch(
            _seg_select + """
            WHERE ts.started_at >= $1 AND ts.started_at < $2
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IS NOT NULL
              AND ts.segment_type != 'idle'
            GROUP BY ts.segment_type
            """,
            since, until,
        )
        daily_rows = await conn.fetch(
            """
            SELECT
              t.day,
              SUM(LEAST(t.loaded_cnt, t.empty_cnt)) AS cnt
            FROM (
              SELECT
                DATE(ts.started_at AT TIME ZONE 'Asia/Shanghai') AS day,
                ts.vehicle_id,
                COUNT(*) FILTER (WHERE ts.segment_type = 'transport_loaded') AS loaded_cnt,
                COUNT(*) FILTER (WHERE ts.segment_type = 'transport_empty') AS empty_cnt
              FROM track_segment ts
              WHERE ts.started_at >= $1 AND ts.started_at < $2
                AND ts.ended_at IS NOT NULL
                AND ts.segment_type IN ('transport_loaded', 'transport_empty')
              GROUP BY day, ts.vehicle_id
            ) t
            GROUP BY t.day ORDER BY t.day
            """,
            since, until,
        )
    else:
        mileage_rows = await conn.fetch(
            _seg_select + """
            JOIN vehicle v ON v.id = ts.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $3
            WHERE ts.started_at >= $1 AND ts.started_at < $2
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IS NOT NULL
              AND ts.segment_type != 'idle'
            GROUP BY ts.segment_type
            """,
            since, until, fid,
        )
        daily_rows = await conn.fetch(
            """
            SELECT
              t.day,
              SUM(LEAST(t.loaded_cnt, t.empty_cnt)) AS cnt
            FROM (
              SELECT
                DATE(ts.started_at AT TIME ZONE 'Asia/Shanghai') AS day,
                ts.vehicle_id,
                COUNT(*) FILTER (WHERE ts.segment_type = 'transport_loaded') AS loaded_cnt,
                COUNT(*) FILTER (WHERE ts.segment_type = 'transport_empty') AS empty_cnt
              FROM track_segment ts
              JOIN vehicle v ON v.id = ts.vehicle_id
                AND v.deleted_at IS NULL AND v.fleet_id = $3
              WHERE ts.started_at >= $1 AND ts.started_at < $2
                AND ts.ended_at IS NOT NULL
                AND ts.segment_type IN ('transport_loaded', 'transport_empty')
              GROUP BY day, ts.vehicle_id
            ) t
            GROUP BY t.day ORDER BY t.day
            """,
            since, until, fid,
        )

    mileage_by_type = {
        r["segment_type"]: {
            "total_km": round(float(r["total_km"]), 1),
            "total_min": round(float(r["total_min"]), 0),
            "count": int(r["cnt"]),
        }
        for r in mileage_rows
    }
    daily_trips = [
        {"day": str(r["day"]), "count": int(r["cnt"])}
        for r in daily_rows
    ]

    return ok({"mileage_by_type": mileage_by_type, "daily_trips": daily_trips})


# ─────────────────────────────────────────────────────────────────────────────
# 3. 告警统计
# ─────────────────────────────────────────────────────────────────────────────

_WARN_OVERSPEED    = "('overspeed')"
_WARN_BLIND        = "('oncoming_warn')"
_WARN_OUT_BOUNDS   = "('geofence_violation','ban_violation')"
_WARN_ALL          = "('overspeed','oncoming_warn','geofence_violation','ban_violation')"


@router.get("/alarm-stats")
async def get_alarm_stats(
    from_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD，默认近30天"),
    to_date: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD（含当天）"),
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """预警统计：超速 / 盲区 / 超界 + 每日趋势（可指定日期范围）"""
    fid = _fleet_id(session)
    since, until = _parse_range(from_date, to_date)

    # asyncpg 单连接不支持并发，顺序执行三条计数查询
    if fid is None:
        overspeed_cnt = await conn.fetchval(
            f"SELECT COUNT(*) FROM event WHERE occurred_at >= $1 AND occurred_at < $2 AND event_type IN {_WARN_OVERSPEED}",
            since, until,
        )
        blind_cnt = await conn.fetchval(
            f"SELECT COUNT(*) FROM event WHERE occurred_at >= $1 AND occurred_at < $2 AND event_type IN {_WARN_BLIND}",
            since, until,
        )
        oob_cnt = await conn.fetchval(
            f"SELECT COUNT(*) FROM event WHERE occurred_at >= $1 AND occurred_at < $2 AND event_type IN {_WARN_OUT_BOUNDS}",
            since, until,
        )
    else:
        overspeed_cnt = await conn.fetchval(
            f"""SELECT COUNT(*) FROM event e
                JOIN vehicle v ON v.id = e.vehicle_id AND v.deleted_at IS NULL AND v.fleet_id = $3
                WHERE e.occurred_at >= $1 AND e.occurred_at < $2 AND e.event_type IN {_WARN_OVERSPEED}""",
            since, until, fid,
        )
        blind_cnt = await conn.fetchval(
            f"""SELECT COUNT(*) FROM event e
                JOIN vehicle v ON v.id = e.vehicle_id AND v.deleted_at IS NULL AND v.fleet_id = $3
                WHERE e.occurred_at >= $1 AND e.occurred_at < $2 AND e.event_type IN {_WARN_BLIND}""",
            since, until, fid,
        )
        oob_cnt = await conn.fetchval(
            f"""SELECT COUNT(*) FROM event e
                JOIN vehicle v ON v.id = e.vehicle_id AND v.deleted_at IS NULL AND v.fleet_id = $3
                WHERE e.occurred_at >= $1 AND e.occurred_at < $2 AND e.event_type IN {_WARN_OUT_BOUNDS}""",
            since, until, fid,
        )

    # 每日趋势（三类合并）
    if fid is None:
        daily_rows = await conn.fetch(
            f"""
            SELECT DATE(occurred_at AT TIME ZONE 'Asia/Shanghai') AS day, COUNT(*) AS cnt
            FROM event
            WHERE occurred_at >= $1 AND occurred_at < $2 AND event_type IN {_WARN_ALL}
            GROUP BY day ORDER BY day
            """,
            since, until,
        )
    else:
        daily_rows = await conn.fetch(
            f"""
            SELECT DATE(e.occurred_at AT TIME ZONE 'Asia/Shanghai') AS day, COUNT(*) AS cnt
            FROM event e
            JOIN vehicle v ON v.id = e.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $3
            WHERE e.occurred_at >= $1 AND e.occurred_at < $2 AND e.event_type IN {_WARN_ALL}
            GROUP BY day ORDER BY day
            """,
            since, until, fid,
        )

    overspeed    = int(overspeed_cnt or 0)
    blind_zone   = int(blind_cnt    or 0)
    out_of_bounds = int(oob_cnt     or 0)
    total = overspeed + blind_zone + out_of_bounds

    return ok({
        "total":         total,
        "overspeed":     overspeed,
        "blind_zone":    blind_zone,
        "out_of_bounds": out_of_bounds,
        "daily": [{"day": str(r["day"]), "count": int(r["cnt"])} for r in daily_rows],
    })


# ─────────────────────────────────────────────────────────────────────────────
# 4. 效率分析
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/efficiency")
async def get_efficiency(
    from_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD，默认近30天"),
    to_date: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD（含当天）"),
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """效率分析：开动率 / 载重占比 / 平均单趟时长 / 往返趟次（可指定日期范围）"""
    fid = _fleet_id(session)
    since, until = _parse_range(from_date, to_date)
    days_count = max((until - since).days, 1)

    if fid is None:
        rows = await conn.fetch(
            """
            SELECT
              ts.segment_type,
              COUNT(*) AS cnt,
              AVG(EXTRACT(EPOCH FROM (ts.ended_at - ts.started_at)) / 60) AS avg_min
            FROM track_segment ts
            WHERE ts.started_at >= $1 AND ts.started_at < $2
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IS NOT NULL
              AND ts.segment_type != 'idle'
            GROUP BY ts.segment_type
            """,
            since, until,
        )
        active_hours = await conn.fetchval(
            """
            SELECT COALESCE(SUM(
              EXTRACT(EPOCH FROM (ts.ended_at - ts.started_at)) / 3600
            ), 0)
            FROM track_segment ts
            WHERE ts.started_at >= $1 AND ts.started_at < $2
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IN ('transport_loaded','transport_empty','loading','unloading')
            """,
            since, until,
        )
        vehicle_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vehicle WHERE deleted_at IS NULL"
        )
        round_trip_total = await conn.fetchval(
            """
            SELECT COALESCE(SUM(LEAST(t.loaded_cnt, t.empty_cnt)), 0)
            FROM (
              SELECT
                ts.vehicle_id,
                COUNT(*) FILTER (WHERE ts.segment_type = 'transport_loaded') AS loaded_cnt,
                COUNT(*) FILTER (WHERE ts.segment_type = 'transport_empty') AS empty_cnt
              FROM track_segment ts
              WHERE ts.started_at >= $1 AND ts.started_at < $2
                AND ts.ended_at IS NOT NULL
                AND ts.segment_type IN ('transport_loaded','transport_empty')
              GROUP BY ts.vehicle_id
            ) t
            """,
            since, until,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT
              ts.segment_type,
              COUNT(*) AS cnt,
              AVG(EXTRACT(EPOCH FROM (ts.ended_at - ts.started_at)) / 60) AS avg_min
            FROM track_segment ts
            JOIN vehicle v ON v.id = ts.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $3
            WHERE ts.started_at >= $1 AND ts.started_at < $2
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IS NOT NULL
              AND ts.segment_type != 'idle'
            GROUP BY ts.segment_type
            """,
            since, until, fid,
        )
        active_hours = await conn.fetchval(
            """
            SELECT COALESCE(SUM(
              EXTRACT(EPOCH FROM (ts.ended_at - ts.started_at)) / 3600
            ), 0)
            FROM track_segment ts
            JOIN vehicle v ON v.id = ts.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $3
            WHERE ts.started_at >= $1 AND ts.started_at < $2
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IN ('transport_loaded','transport_empty','loading','unloading')
            """,
            since, until, fid,
        )
        vehicle_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vehicle WHERE deleted_at IS NULL AND fleet_id = $1",
            fid,
        )
        round_trip_total = await conn.fetchval(
            """
            SELECT COALESCE(SUM(LEAST(t.loaded_cnt, t.empty_cnt)), 0)
            FROM (
              SELECT
                ts.vehicle_id,
                COUNT(*) FILTER (WHERE ts.segment_type = 'transport_loaded') AS loaded_cnt,
                COUNT(*) FILTER (WHERE ts.segment_type = 'transport_empty') AS empty_cnt
              FROM track_segment ts
              JOIN vehicle v ON v.id = ts.vehicle_id
                AND v.deleted_at IS NULL AND v.fleet_id = $3
              WHERE ts.started_at >= $1 AND ts.started_at < $2
                AND ts.ended_at IS NOT NULL
                AND ts.segment_type IN ('transport_loaded','transport_empty')
              GROUP BY ts.vehicle_id
            ) t
            """,
            since, until, fid,
        )

    stats: dict[str, dict] = {}
    for r in rows:
        stats[r["segment_type"]] = {
            "count": int(r["cnt"]),
            "avg_min": round(float(r["avg_min"] or 0), 1),
        }

    loaded = stats.get("transport_loaded", {}).get("count", 0)
    empty = stats.get("transport_empty", {}).get("count", 0)
    loaded_segment_total = loaded + empty
    loaded_ratio = round(loaded / loaded_segment_total * 100, 1) if loaded_segment_total > 0 else 0.0

    transport_avgs = [
        stats[t]["avg_min"]
        for t in ("transport_loaded", "transport_empty")
        if stats.get(t, {}).get("count", 0) > 0
    ]
    avg_transport_min = round(sum(transport_avgs) / len(transport_avgs), 1) if transport_avgs else 0.0

    possible_hours = max(int(vehicle_count or 1), 1) * days_count * 12
    utilization = min(round(float(active_hours or 0) / possible_hours * 100, 1), 99.9)

    return ok({
        "utilization_rate": utilization,
        "loaded_ratio": loaded_ratio,
        "avg_transport_min": avg_transport_min,
        "total_trips": sum(v["count"] for v in stats.values()),
        "transport_trips": int(round_trip_total or 0),
        "type_stats": stats,
    })
