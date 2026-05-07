<!-- 左侧面板3：运输里程统计（饼图 + 五种状态明细） -->
<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import ScreenPanel from './ScreenPanel.vue'
import type { SegmentStats } from '@/api/screen'

const props = defineProps<{ data: SegmentStats | null }>()
const chartRef = ref<HTMLElement | null>(null)
let chart: unknown = null

const STATE_LABELS: Record<string, string> = {
  transport_loaded: '重载运输',
  transport_empty:  '空载运输',
  loading:          '装料',
  unloading:        '卸料',
  unknown:          '未知',
}
const STATE_COLORS: Record<string, string> = {
  transport_loaded: '#38bdf8',
  transport_empty:  '#818cf8',
  loading:          '#34d399',
  unloading:        '#fb923c',
  unknown:          '#6b7280',
}

function buildOption(data: SegmentStats) {
  const byType = data.mileage_by_type
  const pieData = Object.entries(byType).map(([k, v]) => ({
    name: STATE_LABELS[k] ?? k,
    value: v.total_km,
    itemStyle: { color: STATE_COLORS[k] ?? '#999' },
  }))
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(5,20,60,.9)',
      borderColor: 'rgba(0,180,255,.3)',
      textStyle: { color: '#e0f0ff', fontSize: 12 },
      formatter: '{b}: {c} km ({d}%)',
    },
    legend: { show: false },
    series: [{
      type: 'pie',
      radius: ['42%', '70%'],
      center: ['50%', '50%'],
      data: pieData,
      label: {
        show: true,
        position: 'inside',
        fontSize: 10,
        color: 'rgba(255,255,255,.9)',
        formatter: '{d}%',
        minAngle: 8,
      },
      labelLine: { show: false },
      emphasis: { scale: true, scaleSize: 4 },
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
  await nextTick()
  await initChart()
  if (chartRef.value) resizeObs.observe(chartRef.value)
})
onUnmounted(() => {
  resizeObs.disconnect()
  ;(chart as { dispose?(): void } | null)?.dispose?.()
})

function totalKm(data: SegmentStats) {
  return Object.values(data.mileage_by_type)
    .reduce((s, v) => s + v.total_km, 0)
    .toFixed(1)
}
</script>

<template>
  <ScreenPanel title="运输里程 · 近30天">
    <div class="chart-wrap">
      <div ref="chartRef" class="pie-chart" />
    </div>
    <div v-if="data" class="legend-list">
      <div
        v-for="[k, v] in Object.entries(data.mileage_by_type)"
        :key="k"
        class="legend-row"
      >
        <span class="dot" :style="{ background: STATE_COLORS[k] ?? '#999' }" />
        <span class="lname">{{ STATE_LABELS[k] ?? k }}</span>
        <span class="lval">{{ v.total_km.toFixed(1) }} km</span>
        <span class="lcnt">{{ v.count }} 趟</span>
      </div>
    </div>
    <div v-else class="loading">加载中…</div>
  </ScreenPanel>
</template>

<style scoped>
.chart-wrap { height: 130px; flex-shrink: 0; }
.pie-chart  { width: 100%; height: 100%; }

.legend-list {
  overflow-y: auto; padding-top: 4px;
  scrollbar-width: thin; scrollbar-color: rgba(0,180,255,.2) transparent;
}
.legend-row {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 2px; font-size: 11px;
  border-bottom: 1px solid rgba(0,80,160,.15);
}
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.lname { color: rgba(180,220,255,.85); flex: 1; white-space: nowrap; }
.lval  { color: #38bdf8; font-weight: 600; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.lcnt  { color: rgba(100,160,200,.5); min-width: 32px; text-align: right; flex-shrink: 0; }

.loading { color: rgba(100,160,200,.4); font-size: 12px; text-align: center; padding: 20px; }
</style>
