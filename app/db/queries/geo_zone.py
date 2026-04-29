SELECT_ALL_ENABLED_ZONES_SQL = """
    SELECT id, name, zone_type, coordinates, speed_limit, dwell_min, is_enabled, extra, notes
    FROM geo_zone
    WHERE is_enabled = TRUE
    ORDER BY id
"""

SELECT_ZONE_BY_ID_SQL = """
    SELECT id, name, zone_type, coordinates, speed_limit, dwell_min, is_enabled, extra, notes
    FROM geo_zone
    WHERE id = $1
"""

SELECT_ALL_ZONES_SQL = """
    SELECT id, name, zone_type, coordinates, speed_limit, dwell_min, is_enabled, extra, notes,
           created_at
    FROM geo_zone
    ORDER BY id DESC
"""

INSERT_ZONE_SQL = """
    INSERT INTO geo_zone (name, zone_type, coordinates, speed_limit, dwell_min, is_enabled, notes)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING id
"""

UPDATE_ZONE_SQL = """
    UPDATE geo_zone
    SET name        = COALESCE($2, name),
        zone_type   = COALESCE($3, zone_type),
        coordinates = COALESCE($4, coordinates),
        speed_limit = COALESCE($5, speed_limit),
        dwell_min   = COALESCE($6, dwell_min),
        is_enabled  = COALESCE($7, is_enabled),
        notes       = COALESCE($8, notes)
    WHERE id = $1
"""

DELETE_ZONE_SQL = """
    DELETE FROM geo_zone WHERE id = $1
"""
