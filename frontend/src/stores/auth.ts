import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { SessionData, UserRole } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const session = ref<SessionData | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => session.value !== null)
  const role = computed<UserRole | null>(() => session.value?.role ?? null)
  const fleetId = computed<number | null>(() => session.value?.fleet_id ?? null)
  const isManager = computed(() => session.value?.role === 'manager')
  const isFleetCaptain = computed(() => session.value?.role === 'fleet_captain')

  async function fetchMe(): Promise<boolean> {
    try {
      session.value = await authApi.me()
      return true
    } catch {
      session.value = null
      return false
    }
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true
    try {
      session.value = await authApi.login({ username, password })
    } finally {
      loading.value = false
    }
  }

  async function logout(): Promise<void> {
    try {
      await authApi.logout()
    } finally {
      session.value = null
    }
  }

  return {
    session,
    loading,
    isLoggedIn,
    role,
    fleetId,
    isManager,
    isFleetCaptain,
    fetchMe,
    login,
    logout,
  }
})
