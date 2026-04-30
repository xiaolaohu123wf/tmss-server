import { get, post, put, patch, del } from './index'
import type { Fleet, FleetCreate, FleetCreateResult, FleetUpdate, FleetMe, FleetMeUpdate } from '@/types'

export const fleetsApi = {
  list: () =>
    get<Fleet[]>('/admin/fleets'),

  create: (data: FleetCreate) =>
    post<FleetCreateResult>('/admin/fleets', data),

  update: (id: number, data: FleetUpdate) =>
    put<Fleet>(`/admin/fleets/${id}`, data),

  delete: (id: number) =>
    del(`/admin/fleets/${id}`),

  getMyFleet: () =>
    get<FleetMe | null>('/fleets/me'),

  updateMyFleet: (data: FleetMeUpdate) =>
    patch<FleetMe>('/fleets/me', data),
}
