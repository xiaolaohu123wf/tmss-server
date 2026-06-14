INSERT_SEGMENT_SQL = """
    INSERT INTO track_segment (device_id, vehicle_id, started_at, start_lat, start_lng, segment_type)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id
"""

CLOSE_SEGMENT_SQL = """
    UPDATE track_segment
    SET ended_at    = $2,
        end_lat     = $3,
        end_lng     = $4,
        point_count = point_count + $5
    WHERE id = $1
      AND ended_at IS NULL
"""

UPDATE_SEGMENT_TYPE_SQL = """
    UPDATE track_segment
    SET segment_type = $2
    WHERE id = $1
"""

UPDATE_SEGMENT_START_SQL = """
    UPDATE track_segment
    SET started_at = $2,
        start_lat  = $3,
        start_lng  = $4
    WHERE id = $1
"""

INCREMENT_SEGMENT_POINTS_SQL = """
    UPDATE track_segment
    SET point_count = point_count + 1
    WHERE id = $1
"""

# 段关闭后立即计算并持久化里程，避免列表查询每次扫描 location_point。
# 使用 B-tree 复合索引 idx_lp_device_time (device_id, recorded_at) 做顺序范围扫描。
# 仅在 ended_at IS NOT NULL 时执行，开放段（实时进行中）不更新。
COMPUTE_DISTANCE_SQL = """
    WITH ordered AS (
        SELECT
            lp.lat::DOUBLE PRECISION                                AS lat,
            lp.lng::DOUBLE PRECISION                                AS lng,
            LAG(lp.lat::DOUBLE PRECISION)
                OVER (ORDER BY lp.recorded_at, lp.id)               AS prev_lat,
            LAG(lp.lng::DOUBLE PRECISION)
                OVER (ORDER BY lp.recorded_at, lp.id)               AS prev_lng
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
            CASE
                WHEN prev_lat IS NULL THEN 0.0
                ELSE 6371.0088 * ACOS(
                    LEAST(1.0, GREATEST(-1.0,
                          SIN(RADIANS(prev_lat)) * SIN(RADIANS(lat))
                        + COS(RADIANS(prev_lat)) * COS(RADIANS(lat))
                          * COS(RADIANS(lng - prev_lng))
                    ))
                )
            END
        ), 0.0)
        FROM ordered
    )
    WHERE id = $1
      AND ended_at IS NOT NULL
"""

SELECT_OPEN_SEGMENT_BY_DEVICE_SQL = """
    SELECT id, device_id, vehicle_id, started_at, start_lat, start_lng, point_count, segment_type
    FROM track_segment
    WHERE device_id = $1
      AND ended_at IS NULL
    ORDER BY started_at DESC
    LIMIT 1
"""
