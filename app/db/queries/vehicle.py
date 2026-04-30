_VEHICLE_SELECT = """
    SELECT v.id, v.fleet_id, v.license_plate, v.vehicle_type,
           v.load_capacity, v.notes, v.driver_name, v.created_at,
           f.name  AS fleet_name,
           dvb.vehicle_id IS NOT NULL AS has_device,
           d.id    AS device_id,
           d.imei  AS device_imei
    FROM vehicle v
    LEFT JOIN fleet f
           ON f.id = v.fleet_id
    LEFT JOIN device_vehicle_bind dvb
           ON dvb.vehicle_id = v.id AND dvb.unbound_at IS NULL
    LEFT JOIN device d
           ON d.id = dvb.device_id AND d.deleted_at IS NULL
"""

SELECT_ALL_VEHICLES_SQL = _VEHICLE_SELECT + """
    WHERE v.deleted_at IS NULL
    ORDER BY v.id DESC
"""

SELECT_VEHICLES_BY_FLEET_SQL = _VEHICLE_SELECT + """
    WHERE v.fleet_id = $1
      AND v.deleted_at IS NULL
    ORDER BY v.id DESC
"""

SELECT_VEHICLE_BY_ID_SQL = _VEHICLE_SELECT + """
    WHERE v.id = $1
      AND v.deleted_at IS NULL
"""

INSERT_VEHICLE_SQL = """
    INSERT INTO vehicle (fleet_id, license_plate, vehicle_type, load_capacity, notes, driver_name)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id
"""

UPDATE_VEHICLE_SQL = """
    UPDATE vehicle
    SET license_plate = COALESCE($2, license_plate),
        vehicle_type  = COALESCE($3, vehicle_type),
        load_capacity = CASE
            WHEN TRIM(COALESCE($3, vehicle_type)) = 'passenger_car' THEN NULL
            ELSE COALESCE($4, load_capacity)
        END,
        notes         = COALESCE($5, notes),
        fleet_id      = COALESCE($6, fleet_id),
        driver_name   = $7
    WHERE id = $1
      AND deleted_at IS NULL
"""

SOFT_DELETE_VEHICLE_SQL = """
    UPDATE vehicle
    SET deleted_at = NOW()
    WHERE id = $1
      AND deleted_at IS NULL
"""
