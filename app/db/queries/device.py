SELECT_DEVICE_BY_IMEI_SQL = """
    SELECT id, imei, iccid, model, firmware_version, notes, deleted_at
    FROM device
    WHERE imei = $1
"""

# 恢复软删除的设备（TCP 连接时 / 管理员重新添加时使用）
RESTORE_DEVICE_SQL = """
    UPDATE device
    SET deleted_at = NULL
    WHERE imei = $1
      AND deleted_at IS NOT NULL
    RETURNING id
"""

SELECT_DEVICE_BY_ID_SQL = """
    SELECT id, imei, iccid, model, firmware_version, notes, deleted_at
    FROM device
    WHERE id = $1
      AND deleted_at IS NULL
"""

SELECT_ALL_DEVICES_SQL = """
    SELECT d.id, d.imei, d.iccid, d.model, d.firmware_version, d.notes, d.created_at,
           dvb.vehicle_id,
           v.license_plate AS vehicle_license,
           v.fleet_id      AS fleet_id
    FROM device d
    LEFT JOIN device_vehicle_bind dvb
           ON dvb.device_id = d.id AND dvb.unbound_at IS NULL
    LEFT JOIN vehicle v
           ON v.id = dvb.vehicle_id
    WHERE d.deleted_at IS NULL
    ORDER BY d.id DESC
"""

# 强依赖复合索引：CREATE INDEX CONCURRENTLY idx_lp_device_time
#   ON location_point (device_id, recorded_at DESC);
# 有该索引时，LATERAL + LIMIT 1 对每台设备做独立 Index Scan，
# 比全量 DISTINCT ON 少扫描几个数量级的行数。
SELECT_LATEST_LOCATION_PER_DEVICE_SQL = """
    SELECT lp.device_id, lp.loc_type, lp.lat, lp.lng, lp.speed, lp.recorded_at
    FROM   unnest($1::int[]) AS ids(device_id)
    CROSS  JOIN LATERAL (
        SELECT device_id, loc_type, lat, lng, speed, recorded_at
        FROM   location_point
        WHERE  device_id = ids.device_id
        ORDER  BY recorded_at DESC
        LIMIT  1
    ) lp
"""

UPDATE_DEVICE_METADATA_SQL = """
    UPDATE device
    SET firmware_version = NULLIF(trim(COALESCE($2::text, '')), ''),
        iccid            = NULLIF(trim(COALESCE($3::text, '')), '')
    WHERE id = $1
      AND deleted_at IS NULL
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

PATCH_ICCID_IF_EMPTY_SQL = """
    UPDATE device
    SET iccid = $2
    WHERE id = $1
      AND deleted_at IS NULL
      AND (
          iccid IS NULL
          OR btrim(iccid::text) = ''
          OR lower(btrim(iccid::text)) IN ('na', 'n/a', '--')
      )
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

UNBIND_BY_VEHICLE_SQL = """
    UPDATE device_vehicle_bind
    SET unbound_at = NOW()
    WHERE vehicle_id = $1
      AND unbound_at IS NULL
"""

SELECT_DEVICES_BY_FLEET_SQL = """
    SELECT d.id, d.imei, d.iccid, d.model, d.firmware_version, d.notes, d.created_at,
           dvb.vehicle_id,
           v.license_plate AS vehicle_license,
           v.fleet_id      AS fleet_id
    FROM device d
    INNER JOIN device_vehicle_bind dvb
           ON dvb.device_id = d.id AND dvb.unbound_at IS NULL
    INNER JOIN vehicle v
           ON v.id = dvb.vehicle_id
    WHERE d.deleted_at IS NULL
      AND v.fleet_id = $1
    ORDER BY d.id DESC
"""

SELECT_UNBOUND_DEVICES_SQL = """
    SELECT d.id, d.imei, d.iccid, d.model, d.firmware_version, d.notes, d.created_at,
           NULL::int    AS vehicle_id,
           NULL::varchar AS vehicle_license
    FROM device d
    WHERE d.deleted_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM device_vehicle_bind dvb
          WHERE dvb.device_id = d.id AND dvb.unbound_at IS NULL
      )
    ORDER BY d.id DESC
"""
