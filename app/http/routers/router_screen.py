from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends

from app.cache.session_repo import SessionData
from app.core.enums import UserRole
from app.db.deps import get_db_conn
from app.http.deps import require_fleet_or_above
from app.http.response import ok

router = APIRouter(prefix="/api/screen", tags=["screen"])

# 大屏：terminal 角色不可访问，复用 require_fleet_or_above（已包含 fleet_captain+manager）


def _fleet_id(session: SessionData) -> Optional[int]:
    return None if session.role == UserRole.MANAGER else session.fleet_id


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
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """
    近30天运输里程（按5种状态分组，直线×1.2修正）+
    每日运输趟次（transport_loaded + transport_empty）
    """
    fid = _fleet_id(session)
    since = datetime.now(tz=timezone.utc) - timedelta(days=30)

    if fid is None:
        mileage_rows = await conn.fetch(
            """
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
              COUNT(*) AS cnt
            FROM track_segment ts
            WHERE ts.started_at >= $1
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IS NOT NULL
              AND ts.segment_type != 'idle'
            GROUP BY ts.segment_type
            """,
            since,
        )
        daily_rows = await conn.fetch(
            """
            SELECT
              DATE(ts.started_at AT TIME ZONE 'Asia/Shanghai') AS day,
              COUNT(*) AS cnt
            FROM track_segment ts
            WHERE ts.started_at >= $1
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IN ('transport_loaded', 'transport_empty')
            GROUP BY day ORDER BY day
            """,
            since,
        )
    else:
        mileage_rows = await conn.fetch(
            """
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
              COUNT(*) AS cnt
            FROM track_segment ts
            JOIN vehicle v ON v.id = ts.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $2
            WHERE ts.started_at >= $1
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IS NOT NULL
              AND ts.segment_type != 'idle'
            GROUP BY ts.segment_type
            """,
            since,
            fid,
        )
        daily_rows = await conn.fetch(
            """
            SELECT
              DATE(ts.started_at AT TIME ZONE 'Asia/Shanghai') AS day,
              COUNT(*) AS cnt
            FROM track_segment ts
            JOIN vehicle v ON v.id = ts.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $2
            WHERE ts.started_at >= $1
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IN ('transport_loaded', 'transport_empty')
            GROUP BY day ORDER BY day
            """,
            since,
            fid,
        )

    mileage_by_type = {
        r["segment_type"]: {
            "total_km": round(float(r["total_km"]), 1),
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
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """
    近30天预警统计：
    - overspeed     超速预警
    - blind_zone    盲区提醒预警（oncoming_warn）
    - out_of_bounds 超界预警（geofence_violation + ban_violation）
    + 每日趋势
    """
    fid = _fleet_id(session)
    since = datetime.now(tz=timezone.utc) - timedelta(days=30)

    def _build_count_sql(fid_filter: bool, event_types: str) -> tuple[str, list]:
        if fid_filter:
            return (
                f"""
                SELECT COUNT(*) AS cnt
                FROM event e
                JOIN vehicle v ON v.id = e.vehicle_id
                  AND v.deleted_at IS NULL AND v.fleet_id = $2
                WHERE e.occurred_at >= $1 AND e.event_type IN {event_types}
                """,
                [since, fid],
            )
        return (
            f"""
            SELECT COUNT(*) AS cnt FROM event
            WHERE occurred_at >= $1 AND event_type IN {event_types}
            """,
            [since],
        )

    sql_spd, args_spd   = _build_count_sql(fid is not None, _WARN_OVERSPEED)
    sql_bld, args_bld   = _build_count_sql(fid is not None, _WARN_BLIND)
    sql_oob, args_oob   = _build_count_sql(fid is not None, _WARN_OUT_BOUNDS)

    overspeed_cnt, blind_cnt, oob_cnt = await asyncio.gather(
        conn.fetchval(sql_spd, *args_spd),
        conn.fetchval(sql_bld, *args_bld),
        conn.fetchval(sql_oob, *args_oob),
    )

    # 每日趋势（三类合并）
    if fid is None:
        daily_rows = await conn.fetch(
            f"""
            SELECT DATE(occurred_at AT TIME ZONE 'Asia/Shanghai') AS day, COUNT(*) AS cnt
            FROM event
            WHERE occurred_at >= $1 AND event_type IN {_WARN_ALL}
            GROUP BY day ORDER BY day
            """,
            since,
        )
    else:
        daily_rows = await conn.fetch(
            f"""
            SELECT DATE(e.occurred_at AT TIME ZONE 'Asia/Shanghai') AS day, COUNT(*) AS cnt
            FROM event e
            JOIN vehicle v ON v.id = e.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $2
            WHERE e.occurred_at >= $1 AND e.event_type IN {_WARN_ALL}
            GROUP BY day ORDER BY day
            """,
            since,
            fid,
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
    session: SessionData = Depends(require_fleet_or_above),
    conn: asyncpg.Connection = Depends(get_db_conn),  # type: ignore[type-arg]
) -> dict:
    """
    近30天效率分析：
    - 开动率 = 有效作业时长 / (车辆数 × 30天 × 12h)
    - 载重趟次占比 = transport_loaded / (loaded + empty)
    - 平均单趟运输时长（分钟）
    """
    fid = _fleet_id(session)
    since = datetime.now(tz=timezone.utc) - timedelta(days=30)

    if fid is None:
        rows = await conn.fetch(
            """
            SELECT
              ts.segment_type,
              COUNT(*) AS cnt,
              AVG(EXTRACT(EPOCH FROM (ts.ended_at - ts.started_at)) / 60) AS avg_min
            FROM track_segment ts
            WHERE ts.started_at >= $1
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IS NOT NULL
              AND ts.segment_type != 'idle'
            GROUP BY ts.segment_type
            """,
            since,
        )
        active_hours = await conn.fetchval(
            """
            SELECT COALESCE(SUM(
              EXTRACT(EPOCH FROM (ts.ended_at - ts.started_at)) / 3600
            ), 0)
            FROM track_segment ts
            WHERE ts.started_at >= $1
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IN ('transport_loaded','transport_empty','loading','unloading')
            """,
            since,
        )
        vehicle_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vehicle WHERE deleted_at IS NULL"
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
              AND v.deleted_at IS NULL AND v.fleet_id = $2
            WHERE ts.started_at >= $1
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IS NOT NULL
              AND ts.segment_type != 'idle'
            GROUP BY ts.segment_type
            """,
            since,
            fid,
        )
        active_hours = await conn.fetchval(
            """
            SELECT COALESCE(SUM(
              EXTRACT(EPOCH FROM (ts.ended_at - ts.started_at)) / 3600
            ), 0)
            FROM track_segment ts
            JOIN vehicle v ON v.id = ts.vehicle_id
              AND v.deleted_at IS NULL AND v.fleet_id = $2
            WHERE ts.started_at >= $1
              AND ts.ended_at IS NOT NULL
              AND ts.segment_type IN ('transport_loaded','transport_empty','loading','unloading')
            """,
            since,
            fid,
        )
        vehicle_count = await conn.fetchval(
            "SELECT COUNT(*) FROM vehicle WHERE deleted_at IS NULL AND fleet_id = $1",
            fid,
        )

    stats: dict[str, dict] = {}
    for r in rows:
        stats[r["segment_type"]] = {
            "count": int(r["cnt"]),
            "avg_min": round(float(r["avg_min"] or 0), 1),
        }

    loaded = stats.get("transport_loaded", {}).get("count", 0)
    empty = stats.get("transport_empty", {}).get("count", 0)
    transport_total = loaded + empty
    loaded_ratio = round(loaded / transport_total * 100, 1) if transport_total > 0 else 0.0

    transport_avgs = [
        stats[t]["avg_min"]
        for t in ("transport_loaded", "transport_empty")
        if stats.get(t, {}).get("count", 0) > 0
    ]
    avg_transport_min = round(sum(transport_avgs) / len(transport_avgs), 1) if transport_avgs else 0.0

    possible_hours = max(int(vehicle_count or 1), 1) * 30 * 12
    utilization = min(round(float(active_hours or 0) / possible_hours * 100, 1), 99.9)

    return ok({
        "utilization_rate": utilization,
        "loaded_ratio": loaded_ratio,
        "avg_transport_min": avg_transport_min,
        "total_trips": sum(v["count"] for v in stats.values()),
        "transport_trips": transport_total,
        "type_stats": stats,
    })
