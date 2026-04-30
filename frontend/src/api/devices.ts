import { get, post } from './index'
import type { Device, DeviceCreate } from '@/types'

export const devicesApi = {
  list: () =>
    get<Device[]>('/devices'),

  create: (data: DeviceCreate) =>
    post<Device>('/devices', data),

  bind: (deviceId: number, vehicleId: number) =>
    post<null>(`/devices/${deviceId}/bind`, { vehicle_id: vehicleId }),

  unbind: (deviceId: number) =>
    post<null>(`/devices/${deviceId}/unbind`),

  sendCommand: (deviceId: number, command: string) =>
    post<null>(`/devices/${deviceId}/command`, { command }),
}
