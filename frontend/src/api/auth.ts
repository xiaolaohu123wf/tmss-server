import { get, post } from './index'
import type { SessionData } from '@/types'

export interface LoginRequest {
  username: string
  password: string
}

export const authApi = {
  login: (data: LoginRequest) =>
    post<SessionData>('/auth/login', data),

  logout: () =>
    post<null>('/auth/logout'),

  me: () =>
    get<SessionData>('/auth/me'),
}
