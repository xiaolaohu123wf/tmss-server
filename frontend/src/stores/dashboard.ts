import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { VehiclePosition, AlertFrame } from '@/types'

export const useDashboardStore = defineStore('dashboard', () => {
  // vehicleId → latest position
  const positions = ref<Map<number, VehiclePosition>>(new Map())
  // recent alerts (keep last 50)
  const alerts = ref<AlertFrame[]>([])
  const onlineCount = computed(() => positions.value.size)

  function updatePosition(frame: VehiclePosition): void {
    const key = frame.vehicle_id ?? frame.device_id
    positions.value.set(key, frame)
  }

  function addAlert(frame: AlertFrame): void {
    alerts.value.unshift(frame)
    if (alerts.value.length > 50) {
      alerts.value.pop()
    }
  }

  function clearAlerts(): void {
    alerts.value = []
  }

  const positionList = computed(() => Array.from(positions.value.values()))

  return {
    positions,
    alerts,
    onlineCount,
    positionList,
    updatePosition,
    addAlert,
    clearAlerts,
  }
})
