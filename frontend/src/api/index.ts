import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import type { ApiResponse } from '@/types'

const instance: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 15000,
  withCredentials: true, // 携带 Cookie (tmss_session)
})

// Response interceptor: parse { ok, data } / { ok, code, message }
instance.interceptors.response.use(
  (response) => {
    const res = response.data as ApiResponse<unknown>
    if (!res.ok) {
      const msg = res.message ?? '请求失败'
      ElMessage.error(msg)
      return Promise.reject(new Error(msg))
    }
    return response
  },
  (error) => {
    const status = error.response?.status
    if (status === 401 || status === 403) {
      // Session 过期或无权限 → 跳转登录
      const { pathname } = window.location
      if (pathname !== '/login') {
        ElMessage.warning('会话已过期，请重新登录')
        window.location.href = '/login'
      }
    } else {
      ElMessage.error(error.response?.data?.message ?? '网络错误')
    }
    return Promise.reject(error)
  },
)

/** 提取 data 字段的辅助函数 */
export async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await instance.get<ApiResponse<T>>(url, config)
  return (res.data as { ok: true; data: T }).data
}

export async function post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await instance.post<ApiResponse<T>>(url, data, config)
  return (res.data as { ok: true; data: T }).data
}

export async function put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await instance.put<ApiResponse<T>>(url, data, config)
  return (res.data as { ok: true; data: T }).data
}

export async function patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const res = await instance.patch<ApiResponse<T>>(url, data, config)
  return (res.data as { ok: true; data: T }).data
}

export async function del<T = null>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const res = await instance.delete<ApiResponse<T>>(url, config)
  return (res.data as { ok: true; data: T }).data
}

export default instance
