SELECT_VEHICLES_BY_FLEET_SQL = """
    SELECT id, fleet_id, license_plate, vehicle_type, load_capacity, notes, created_at
    FROM vehicle
    WHERE fleet_id = $1
      AND deleted_at IS NULL
    ORDER BY id DESC
"""

SELECT_ALL_VEHICLES_SQL = """
    SELECT id, fleet_id, license_plate, vehicle_type, load_capacity, notes, created_at
    FROM vehicle
    WHERE deleted_at IS NULL
    ORDER BY id DESC
"""

SELECT_VEHICLE_BY_ID_SQL = """
    SELECT id, fleet_id, license_plate, vehicle_type, load_capacity, notes, created_at
    FROM vehicle
    WHERE id = $1
      AND deleted_at IS NULL
"""

INSERT_VEHICLE_SQL = """
    INSERT INTO vehicle (fleet_id, license_plate, vehicle_type, load_capacity, notes)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING id
"""

UPDATE_VEHICLE_SQL = """
    UPDATE vehicle
    SET license_plate = COALESCE($2, license_plate),
        vehicle_type  = COALESCE($3, vehicle_type),
        load_capacity = COALESCE($4, load_capacity),
        notes         = COALESCE($5, notes),
        fleet_id      = COALESCE($6, fleet_id)
    WHERE id = $1
      AND deleted_at IS NULL
"""

SOFT_DELETE_VEHICLE_SQL = """
    UPDATE vehicle
    SET deleted_at = NOW()
    WHERE id = $1
      AND deleted_at IS NULL
"""
