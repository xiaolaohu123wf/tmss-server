import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { screenApi } from '@/api/screen'
import type { ScreenSummary, SegmentStats, AlarmStats, EfficiencyStats } from '@/api/screen'

function toDateStr(d: Date) {
  return d.toISOString().slice(0, 10)
}

export const useScreenStore = defineStore('screen', () => {
  const summary     = ref<ScreenSummary | null>(null)
  const segmentStats = ref<SegmentStats | null>(null)
  const alarmStats  = ref<AlarmStats | null>(null)
  const efficiency  = ref<EfficiencyStats | null>(null)
  const loading     = ref(false)

  // ── 时间范围（默认近30天） ────────────────────────────────
  const dateTo   = ref(toDateStr(new Date()))
  const dateFrom = ref(toDateStr(new Date(Date.now() - 30 * 86400_000)))

  // 供 el-date-picker v-model 绑定（返回 [string, string]）
  const dateRange = computed<[string, string]>({
    get: () => [dateFrom.value, dateTo.value],
    set: ([from, to]) => {
      dateFrom.value = from
      dateTo.value   = to
    },
  })

  function rangeParams() {
    return { from_date: dateFrom.value, to_date: dateTo.value }
  }

  async function fetchAll() {
    loading.value = true
    const range = rangeParams()
    try {
      const [s, seg, alarm, eff] = await Promise.all([
        screenApi.summary(),
        screenApi.segmentStats(range),
        screenApi.alarmStats(range),
        screenApi.efficiency(range),
      ])
      summary.value      = s
      segmentStats.value = seg
      alarmStats.value   = alarm
      efficiency.value   = eff
    } catch (e) {
      console.warn('[screen] fetchAll failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function setDateRange(from: string, to: string) {
    dateFrom.value = from
    dateTo.value   = to
    await fetchAll()
  }

  async function refreshSummary() {
    try {
      summary.value = await screenApi.summary()
    } catch { /* ignore */ }
  }

  return {
    summary, segmentStats, alarmStats, efficiency, loading,
    dateFrom, dateTo, dateRange,
    fetchAll, setDateRange, refreshSummary,
  }
})
