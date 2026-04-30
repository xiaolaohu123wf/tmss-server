import { get, post, put, del } from './index'
import type { Vehicle, VehicleCreate, VehicleUpdate } from '@/types'

export const vehiclesApi = {
  list: () =>
    get<Vehicle[]>('/vehicles'),

  create: (data: VehicleCreate) =>
    post<Vehicle>('/vehicles', data),

  update: (id: number, data: VehicleUpdate) =>
    put<Vehicle>(`/vehicles/${id}`, data),

  delete: (id: number) =>
    del(`/vehicles/${id}`),

  bind: (vehicleId: number, deviceId: number) =>
    post<null>(`/vehicles/${vehicleId}/bind`, { device_id: deviceId }),

  unbind: (vehicleId: number) =>
    post<null>(`/vehicles/${vehicleId}/unbind`),
}
