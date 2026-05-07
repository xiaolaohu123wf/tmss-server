<!-- 右侧面板3：预警次数（超速 / 盲区 / 超界） -->
<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import ScreenPanel from './ScreenPanel.vue'
import type { AlarmStats, DailyCount } from '@/api/screen'

const props = defineProps<{ data: AlarmStats | null }>()
const chartRef = ref<HTMLElement | null>(null)
let chart: unknown = null

const WARN_ITEMS = [
  { key: 'overspeed'    , label: '超速预警',    icon: '🚨', color: '#f87171' },
  { key: 'blind_zone'   , label: '盲区提醒',    icon: '⚠️', color: '#fbbf24' },
  { key: 'out_of_bounds', label: '超界预警',    icon: '🔔', color: '#c084fc' },
] as const

function buildOption(data: AlarmStats) {
  const days = data.daily.map((d: DailyCount) => d.day.slice(5))
  const cnts = data.daily.map((d: DailyCount) => d.count)
  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(5,20,60,.9)',
      borderColor: 'rgba(0,180,255,.3)',
      textStyle: { color: '#e0f0ff', fontSize: 11 },
    },
    grid: { left: 20, right: 8, top: 6, bottom: 18 },
    xAxis: {
      type: 'category', data: days,
      axisLabel: {
        color: 'rgba(150,200,240,.5)', fontSize: 9,
        interval: Math.floor(days.length / 6),
      },
      axisLine: { lineStyle: { color: 'rgba(0,180,255,.2)' } },
    },
    yAxis: {
      type: 'value', minInterval: 1,
      axisLabel: { color: 'rgba(150,200,240,.5)', fontSize: 9 },
      splitLine: { lineStyle: { color: 'rgba(0,100,200,.12)' } },
    },
    series: [{
      type: 'line', data: cnts, smooth: true,
      symbol: 'circle', symbolSize: 3,
      lineStyle: { color: '#f87171', width: 1.5 },
      itemStyle: { color: '#f87171' },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(248,113,113,.25)' },
            { offset: 1, color: 'rgba(248,113,113,.02)' },
          ],
        },
      },
    }],
  }
}

async function initChart() {
  if (!chartRef.value) return
  const echarts = await import('echarts')
  chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  if (props.data) (chart as { setOption(o: unknown): void }).setOption(buildOption(props.data))
}

watch(() => props.data, (val) => {
  if (val && chart) (chart as { setOption(o: unknown): void }).setOption(buildOption(val))
})

const resizeObs = new ResizeObserver(() => {
  (chart as { resize?(): void } | null)?.resize?.()
})

onMounted(async () => {
  await nextTick(); await initChart()
  if (chartRef.value) resizeObs.observe(chartRef.value)
})
onUnmounted(() => {
  resizeObs.disconnect()
  ;(chart as { dispose?(): void } | null)?.dispose?.()
})
</script>

<template>
  <ScreenPanel title="预警次数 · 近30天">
    <div class="alarm-wrap">

      <!-- 三类预警卡片 -->
      <div class="warn-cards">
        <div
          v-for="item in WARN_ITEMS"
          :key="item.key"
          class="warn-card"
          :style="{ '--wc': item.color }"
        >
          <span class="wc-icon">{{ item.icon }}</span>
          <span class="wc-val">{{ data ? data[item.key] : '—' }}</span>
          <span class="wc-label">{{ item.label }}</span>
        </div>
      </div>

      <!-- 合计 -->
      <div v-if="data" class="total-row">
        <span class="t-num">{{ data.total }}</span>
        <span class="t-label">近30天预警合计</span>
      </div>

      <!-- 每日趋势折线 -->
      <div ref="chartRef" class="trend-chart" />

    </div>
  </ScreenPanel>
</template>

<style scoped>
.alarm-wrap { display: flex; flex-direction: column; height: 100%; gap: 6px; }

/* ── 三卡片 ── */
.warn-cards {
  display: flex; gap: 6px; flex-shrink: 0;
}
.warn-card {
  flex: 1;
  background: rgba(0,20,60,.5);
  border: 1px solid color-mix(in srgb, var(--wc) 25%, transparent);
  border-radius: 6px;
  display: flex; flex-direction: column; align-items: center;
  padding: 8px 4px; gap: 2px;
  transition: border-color .2s;
}
.warn-card:hover { border-color: var(--wc); }
.wc-icon { font-size: 16px; line-height: 1; }
.wc-val  {
  font-size: 22px; font-weight: 700;
  color: var(--wc); font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.wc-label { font-size: 10px; color: rgba(180,210,240,.6); }

/* ── 合计行 ── */
.total-row {
  display: flex; align-items: baseline; gap: 6px;
  flex-shrink: 0; padding: 0 2px;
}
.t-num { font-size: 20px; font-weight: 700; color: #f87171; font-variant-numeric: tabular-nums; }
.t-label { font-size: 11px; color: rgba(248,113,113,.5); }

/* ── 趋势图 ── */
.trend-chart { flex: 1; min-height: 0; }
</style>
