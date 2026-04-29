INSERT_COMMAND_LOG_SQL = """
    INSERT INTO command_log
        (device_id, vehicle_id, cmd, source, operator_id, event_id, is_delivered, sent_at)
    VALUES ($1, $2, $3, $4, $5, $6, FALSE, NOW())
    RETURNING id
"""

UPDATE_COMMAND_DELIVERED_SQL = """
    UPDATE command_log
    SET is_delivered = TRUE
    WHERE id = $1
"""

SELECT_COMMAND_LOGS_BY_DEVICE_SQL = """
    SELECT id, device_id, vehicle_id, cmd, source, operator_id, event_id, is_delivered, sent_at
    FROM command_log
    WHERE device_id = $1
    ORDER BY sent_at DESC
    LIMIT $2
"""
