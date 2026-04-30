import { get, post, put, del } from './index'
import type { GeoZone, GeoZoneCreate, GeoZoneUpdate } from '@/types'

export const geoZonesApi = {
  list: () =>
    get<GeoZone[]>('/geo-zones'),

  create: (data: GeoZoneCreate) =>
    post<GeoZone>('/geo-zones', data),

  update: (id: number, data: GeoZoneUpdate) =>
    put<GeoZone>(`/geo-zones/${id}`, data),

  delete: (id: number) =>
    del(`/geo-zones/${id}`),

  toggle: (id: number, enabled: boolean) =>
    put<GeoZone>(`/geo-zones/${id}`, { is_enabled: enabled }),
}
