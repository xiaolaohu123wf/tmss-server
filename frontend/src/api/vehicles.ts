import { get, post, put, del } from './index'
import type { Vehicle, VehicleCreate, VehicleUpdate } from '@/types'

/** 后端 Decimal 常为 JSON 字符串，ElInputNumber 需要 number */
function normalizeVehicle(raw: Vehicle): Vehicle {
  const lc = raw.load_capacity as unknown
  if (lc == null || lc === '') return { ...raw, load_capacity: null }
  if (typeof lc === 'number') return Number.isFinite(lc) ? raw : { ...raw, load_capacity: null }
  const n = Number(lc)
  return { ...raw, load_capacity: Number.isFinite(n) ? n : null }
}

export const vehiclesApi = {
  list: () => get<Vehicle[]>('/vehicles').then((rows) => rows.map(normalizeVehicle)),

  create: (data: VehicleCreate) =>
    post<Vehicle>('/vehicles', data).then(normalizeVehicle),

  update: (id: number, data: VehicleUpdate) =>
    put<Vehicle>(`/vehicles/${id}`, data).then(normalizeVehicle),

  delete: (id: number) =>
    del(`/vehicles/${id}`),

  bind: (vehicleId: number, deviceId: number) =>
    post<null>(`/vehicles/${vehicleId}/bind`, { device_id: deviceId }),

  unbind: (vehicleId: number) =>
    post<null>(`/vehicles/${vehicleId}/unbind`),
}
