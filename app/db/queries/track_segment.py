INSERT_SEGMENT_SQL = """
    INSERT INTO track_segment (device_id, vehicle_id, started_at, start_lat, start_lng)
    VALUES ($1, $2, $3, $4, $5)
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

INCREMENT_SEGMENT_POINTS_SQL = """
    UPDATE track_segment
    SET point_count = point_count + 1
    WHERE id = $1
"""

SELECT_OPEN_SEGMENT_BY_DEVICE_SQL = """
    SELECT id, device_id, vehicle_id, started_at, start_lat, start_lng, point_count
    FROM track_segment
    WHERE device_id = $1
      AND ended_at IS NULL
    ORDER BY started_at DESC
    LIMIT 1
"""
