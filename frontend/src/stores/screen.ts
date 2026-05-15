import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { screenApi } from '@/api/screen'
import type { ScreenSummary, SegmentStats, AlarmStats, EfficiencyStats, DailyCount } from '@/api/screen'

function toDateStr(d: Date) {
  return d.toISOString().slice(0, 10)
}

function toUtcDate(d: string) {
  const [y, m, day] = d.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, day))
}

function toDateStrUtc(d: Date) {
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function buildMockAlarmStats(from: string, to: string): AlarmStats {
  const start = toUtcDate(from)
  const end = toUtcDate(to)
  const daily: DailyCount[] = []
  const cursor = new Date(start)

  while (cursor <= end) {
    const day = toDateStrUtc(cursor)
    // 用日期生成稳定模拟值，刷新时不抖动
    const seed = Number(day.replace(/-/g, ''))
    const count = (seed % 7) + 1
    daily.push({ day, count })
    cursor.setDate(cursor.getDate() + 1)
  }

  const total = daily.reduce((sum, item) => sum + item.count, 0)
  const overspeed = Math.round(total * 0.56)
  const blind_zone = Math.round(total * 0.19)
  const out_of_bounds = total - overspeed - blind_zone

  return { total, overspeed, blind_zone, out_of_bounds, daily }
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
      const [s, seg, eff] = await Promise.all([
        screenApi.summary(),
        screenApi.segmentStats(range),
        screenApi.efficiency(range),
      ])
      summary.value      = s
      segmentStats.value = seg
      alarmStats.value   = buildMockAlarmStats(dateFrom.value, dateTo.value)
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
