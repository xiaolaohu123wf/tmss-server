SELECT_BUSINESS_CONFIG_SQL = """
    SELECT global_speed_limit, park_threshold_min,
           alert_cooldown_s, hb_timeout_s,
           weather_city, weather_cache_min,
           map_center_lng, map_center_lat,
           transport_timeout_min, segment_buffer_min
    FROM business_config
    WHERE id = 1
"""
