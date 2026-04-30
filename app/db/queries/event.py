INSERT_EVENT_SQL = """
    INSERT INTO event
        (device_id, vehicle_id, event_type, severity, zone_id, ban_id,
         lat, lng, speed, cmd_sent, detail, occurred_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    RETURNING id
"""

SELECT_EVENTS_BY_VEHICLE_SQL = """
    SELECT id, device_id, vehicle_id, event_type, severity, zone_id,
           lat, lng, speed, cmd_sent, detail, occurred_at
    FROM event
    WHERE vehicle_id = $1
      AND occurred_at >= $2
      AND occurred_at <= $3
    ORDER BY occurred_at DESC
    LIMIT $4 OFFSET $5
"""

SELECT_EVENTS_ALL_SQL = """
    SELECT id, device_id, vehicle_id, event_type, severity, zone_id,
           lat, lng, speed, cmd_sent, detail, occurred_at
    FROM event
    WHERE occurred_at >= $1
      AND occurred_at <= $2
    ORDER BY occurred_at DESC
    LIMIT $3 OFFSET $4
"""

COUNT_EVENTS_BY_VEHICLE_SQL = """
    SELECT COUNT(*) FROM event
    WHERE vehicle_id = $1
      AND occurred_at >= $2
      AND occurred_at <= $3
"""

COUNT_EVENTS_ALL_SQL = """
    SELECT COUNT(*) FROM event
    WHERE occurred_at >= $1
      AND occurred_at <= $2
"""

SELECT_EVENTS_PAGE_SQL = """
    SELECT e.id, e.device_id, e.vehicle_id, e.event_type, e.severity,
           e.zone_id, e.lat, e.lng, e.speed, e.cmd_sent, e.detail, e.occurred_at,
           v.license_plate AS vehicle_license
    FROM event e
    LEFT JOIN vehicle v ON v.id = e.vehicle_id AND v.deleted_at IS NULL
    WHERE ($1::BIGINT IS NULL OR e.vehicle_id = $1)
      AND ($2::VARCHAR IS NULL OR e.event_type = $2)
      AND ($3::TIMESTAMPTZ IS NULL OR e.occurred_at >= $3)
      AND ($4::TIMESTAMPTZ IS NULL OR e.occurred_at <= $4)
      AND ($5::BIGINT IS NULL OR e.vehicle_id IN (
            SELECT id FROM vehicle WHERE fleet_id = $5 AND deleted_at IS NULL
          ))
    ORDER BY e.occurred_at DESC
    LIMIT $6 OFFSET $7
"""

COUNT_EVENTS_PAGE_SQL = """
    SELECT COUNT(*)
    FROM event e
    WHERE ($1::BIGINT IS NULL OR e.vehicle_id = $1)
      AND ($2::VARCHAR IS NULL OR e.event_type = $2)
      AND ($3::TIMESTAMPTZ IS NULL OR e.occurred_at >= $3)
      AND ($4::TIMESTAMPTZ IS NULL OR e.occurred_at <= $4)
      AND ($5::BIGINT IS NULL OR e.vehicle_id IN (
            SELECT id FROM vehicle WHERE fleet_id = $5 AND deleted_at IS NULL
          ))
"""
