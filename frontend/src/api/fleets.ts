import { get, post, put, del } from './index'
import type { Fleet, FleetCreate, FleetUpdate } from '@/types'

export const fleetsApi = {
  list: () =>
    get<Fleet[]>('/admin/fleets'),

  create: (data: FleetCreate) =>
    post<Fleet>('/admin/fleets', data),

  update: (id: number, data: FleetUpdate) =>
    put<Fleet>(`/admin/fleets/${id}`, data),

  delete: (id: number) =>
    del(`/admin/fleets/${id}`),
}
