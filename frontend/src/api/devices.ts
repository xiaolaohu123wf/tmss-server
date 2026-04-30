import { get, post, put, del } from './index'
import type { Device, DeviceCreate } from '@/types'

export const devicesApi = {
  list: (params?: { unbound?: boolean }) =>
    get<Device[]>('/devices', { params }),

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

  /** 管理员：软删除设备 */
  delete: (deviceId: number) => del<{ message: string }>(`/devices/${deviceId}`),
}
