SELECT_DEVICE_BY_IMEI_SQL = """
    SELECT id, imei, iccid, model, firmware_version, notes, deleted_at
    FROM device
    WHERE imei = $1
"""

SELECT_DEVICE_BY_ID_SQL = """
    SELECT id, imei, iccid, model, firmware_version, notes, deleted_at
    FROM device
    WHERE id = $1
      AND deleted_at IS NULL
"""

SELECT_ALL_DEVICES_SQL = """
    SELECT id, imei, iccid, model, firmware_version, notes, created_at
    FROM device
    WHERE deleted_at IS NULL
    ORDER BY id DESC
"""

INSERT_DEVICE_SQL = """
    INSERT INTO device (imei, iccid, model, firmware_version, notes)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING id
"""

UPDATE_DEVICE_FIRMWARE_SQL = """
    UPDATE device
    SET firmware_version = $2,
        iccid            = COALESCE($3, iccid)
    WHERE id = $1
"""

SOFT_DELETE_DEVICE_SQL = """
    UPDATE device
    SET deleted_at = NOW()
    WHERE id = $1
      AND deleted_at IS NULL
"""

SELECT_ACTIVE_BIND_BY_DEVICE_SQL = """
    SELECT id, device_id, vehicle_id, driver_id, bound_at, operator
    FROM device_vehicle_bind
    WHERE device_id = $1
      AND unbound_at IS NULL
"""

SELECT_ACTIVE_BIND_BY_VEHICLE_SQL = """
    SELECT id, device_id, vehicle_id, driver_id, bound_at, operator
    FROM device_vehicle_bind
    WHERE vehicle_id = $1
      AND unbound_at IS NULL
"""

INSERT_BIND_SQL = """
    INSERT INTO device_vehicle_bind (device_id, vehicle_id, driver_id, bound_at, operator)
    VALUES ($1, $2, $3, NOW(), $4)
    RETURNING id
"""

UNBIND_SQL = """
    UPDATE device_vehicle_bind
    SET unbound_at = NOW()
    WHERE device_id = $1
      AND unbound_at IS NULL
"""
