INSERT_WORK_SESSION_SQL = """
    INSERT INTO work_session (vehicle_id, state, zone_id, started_at)
    VALUES ($1, $2, $3, NOW())
    RETURNING id
"""

CLOSE_WORK_SESSION_SQL = """
    UPDATE work_session
    SET ended_at   = NOW(),
        duration_s = EXTRACT(EPOCH FROM (NOW() - started_at))::INT
    WHERE id = $1
      AND ended_at IS NULL
"""

SELECT_OPEN_SESSION_BY_VEHICLE_SQL = """
    SELECT id, vehicle_id, state, zone_id, started_at
    FROM work_session
    WHERE vehicle_id = $1
      AND ended_at IS NULL
    ORDER BY started_at DESC
    LIMIT 1
"""
