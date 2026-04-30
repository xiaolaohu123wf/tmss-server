// ────────────────────────────────────────────────────────────
// Enums (must mirror backend app/core/enums.py)
// ────────────────────────────────────────────────────────────

export type UserRole = 'manager' | 'fleet_captain' | 'terminal'

export type WorkState =
  | 'loading'
  | 'unloading'
  | 'transport_loaded'
  | 'transport_empty'
  | 'unknown'

export type GeoZoneType =
  | 'loading'
  | 'unloading'
  | 'restricted'
  | 'sharp_curve'
  | 'single_bridge'
  | 'speed_zone'

export type EventType =
  | 'overspeed'
  | 'geofence_violation'
  | 'oncoming_warn'
  | 'dispatch'
  | 'ban_violation'
  | 'zone_entry'
  | 'zone_exit'
  | 'device_offline'
  | 'unreported_exit'
  | 'manual_command'

export type LocType = 'gps' | 'lbs'

// ────────────────────────────────────────────────────────────
// Auth / Session
// ────────────────────────────────────────────────────────────

export interface SessionData {
  user_id: number
  username: string
  role: UserRole
  fleet_id: number | null
  issued_at: string
  expires_at: string
}

// ────────────────────────────────────────────────────────────
// Fleet
// ────────────────────────────────────────────────────────────

export interface Fleet {
  id: number
  name: string
  notes: string | null
  created_at: string
}

export interface FleetCreate {
  name: string
  notes?: string
}

export interface FleetUpdate {
  name?: string
  notes?: string
}

// ────────────────────────────────────────────────────────────
// Vehicle
// ────────────────────────────────────────────────────────────

export type VehicleType = 'truck' | 'loader' | 'other'

export interface Vehicle {
  id: number
  fleet_id: number | null
  fleet_name: string | null
  license_plate: string
  vehicle_type: VehicleType
  load_capacity: number | null
  driver_name: string | null
  device_id: number | null
  device_imei: string | null
  notes: string | null
  created_at: string
}

export interface VehicleCreate {
  fleet_id?: number
  license_plate: string
  vehicle_type: VehicleType
  load_capacity?: number
  driver_name?: string
  notes?: string
}

export interface VehicleUpdate {
  license_plate?: string
  vehicle_type?: VehicleType
  load_capacity?: number
  fleet_id?: number
}

// ────────────────────────────────────────────────────────────
// Device
// ────────────────────────────────────────────────────────────

export interface Device {
  id: number
  imei: string
  firmware_version: string | null
  iccid: string | null
  vehicle_id: number | null
  vehicle_license?: string | null
  created_at: string
  // runtime – from device_registry
  online: boolean
  last_heartbeat_at: string | null
  // latest location
  last_loc_type: 'gps' | 'lbs' | null   // null = not yet located
  last_lat: number | null
  last_lng: number | null
  last_location_at: string | null
}

export interface DeviceCreate {
  imei: string
  firmware_version?: string
}

// ────────────────────────────────────────────────────────────
// GeoZone
// ────────────────────────────────────────────────────────────

// Coordinate: [lng, lat]
export type Coordinate = [number, number]

export interface GeoZone {
  id: number
  name: string
  zone_type: GeoZoneType
  coordinates: Coordinate[]
  speed_limit: number | null
  min_stay_seconds: number | null
  is_enabled: boolean
  notes: string | null
  created_at: string
}

export interface GeoZoneCreate {
  name: string
  zone_type: GeoZoneType
  coordinates: Coordinate[]
  speed_limit?: number
  min_stay_seconds?: number
  notes?: string
}

export interface GeoZoneUpdate {
  name?: string
  zone_type?: GeoZoneType
  coordinates?: Coordinate[]
  speed_limit?: number | null
  min_stay_seconds?: number | null
  is_enabled?: boolean
  notes?: string | null
}

// ────────────────────────────────────────────────────────────
// Event / Alert
// ────────────────────────────────────────────────────────────

export interface TmssEvent {
  id: number
  device_id: number | null
  vehicle_id: number | null
  vehicle_license: string | null
  event_type: EventType
  severity: number
  zone_id: number | null
  lat: number | null
  lng: number | null
  speed: number | null
  cmd_sent: string | null
  detail: Record<string, unknown> | null
  occurred_at: string
}

export interface EventQuery {
  vehicle_id?: number
  event_type?: EventType
  // mapped to backend param names
  start?: string
  end?: string
  page?: number
  size?: number
}

export interface PagedResult<T> {
  total: number
  items: T[]
}

// ────────────────────────────────────────────────────────────
// App User
// ────────────────────────────────────────────────────────────

export interface AppUser {
  id: number
  username: string
  role: UserRole
  fleet_id: number | null
  fleet_name?: string | null
  is_active: boolean
  created_at: string
}

export interface UserCreate {
  username: string
  password: string
  role: UserRole
  fleet_id?: number
}

// ────────────────────────────────────────────────────────────
// Dashboard / Real-time
// ────────────────────────────────────────────────────────────

export interface VehiclePosition {
  device_id: number
  vehicle_id: number | null
  fleet_id: number | null
  lat: number
  lng: number
  speed: number | null
  altitude: number | null
  work_state: WorkState
  recorded_at: string
  license_plate?: string
}

export interface AlertFrame {
  device_id: number
  vehicle_id: number | null
  event_type: EventType
  lat: number | null
  lng: number | null
  speed: number | null
  message: string
  created_at: string
  license_plate?: string
}

// ────────────────────────────────────────────────────────────
// API Response wrapper
// ────────────────────────────────────────────────────────────

export interface ApiOk<T> {
  ok: true
  data: T
}

export interface ApiError {
  ok: false
  code: string
  message: string
}

export type ApiResponse<T> = ApiOk<T> | ApiError
