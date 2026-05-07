import { defineStore } from 'pinia'
import { ref } from 'vue'
import { screenApi } from '@/api/screen'
import type { ScreenSummary, SegmentStats, AlarmStats, EfficiencyStats } from '@/api/screen'

export const useScreenStore = defineStore('screen', () => {
  const summary = ref<ScreenSummary | null>(null)
  const segmentStats = ref<SegmentStats | null>(null)
  const alarmStats = ref<AlarmStats | null>(null)
  const efficiency = ref<EfficiencyStats | null>(null)
  const loading = ref(false)

  async function fetchAll() {
    loading.value = true
    try {
      const [s, seg, alarm, eff] = await Promise.all([
        screenApi.summary(),
        screenApi.segmentStats(),
        screenApi.alarmStats(),
        screenApi.efficiency(),
      ])
      summary.value = s
      segmentStats.value = seg
      alarmStats.value = alarm
      efficiency.value = eff
    } catch (e) {
      console.warn('[screen] fetchAll failed:', e)
      // 保留旧数据，不清空
    } finally {
      loading.value = false
    }
  }

  async function refreshSummary() {
    try {
      summary.value = await screenApi.summary()
    } catch { /* ignore */ }
  }

  return { summary, segmentStats, alarmStats, efficiency, loading, fetchAll, refreshSummary }
})
