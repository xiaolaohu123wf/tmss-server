import { get, post, put } from './index'
import type { Device, DeviceCreate } from '@/types'

export const devicesApi = {
  list: () =>
    get<Device[]>('/devices'),

  create: (data: DeviceCreate) =>
    post<Device>('/devices', data),

  update: (deviceId: number, data: { firmware_version: string; iccid: string }) =>
    put<{ message: string }>(`/devices/${deviceId}`, data),

  bind: (deviceId: number, vehicleId: number) =>
    post<null>(`/devices/${deviceId}/bind`, { vehicle_id: vehicleId }),

  unbind: (deviceId: number) =>
    post<null>(`/devices/${deviceId}/unbind`),

  sendCommand: (deviceId: number, command: string) =>
    post<{
      delivered: boolean
      message: string
      speed_kmh_recorded: number | null
    }>(`/devices/${deviceId}/command`, { command }),
}
