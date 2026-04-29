SELECT_ENABLED_BANS_SQL = """
    SELECT id, zone_id, start_time, end_time, weekdays
    FROM operation_ban
    WHERE is_enabled = TRUE
"""
