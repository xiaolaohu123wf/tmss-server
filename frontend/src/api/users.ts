import { get, post, del } from './index'
import type { AppUser, UserCreate } from '@/types'

export const usersApi = {
  list: () =>
    get<AppUser[]>('/users'),

  create: (data: UserCreate) =>
    post<AppUser>('/users', data),

  delete: (id: number) =>
    del(`/users/${id}`),

  changePassword: (id: number, password: string) =>
    post<null>(`/users/${id}/password`, { password }),
}
