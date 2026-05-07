<!-- 左侧面板3：运输里程/时长统计（饼图 + 五种状态明细，可切换维度） -->
<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue'
import ScreenPanel from './ScreenPanel.vue'
import type { SegmentStats } from '@/api/screen'

const props = defineProps<{ data: SegmentStats | null }>()
const chartRef = ref<HTMLElement | null>(null)
let chart: unknown = null

// 切换维度：'km' | 'min'
const mode = ref<'km' | 'min'>('km')

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

const panelTitle = computed(() =>
  mode.value === 'km' ? '运输里程 · 近30天' : '运输时长 · 近30天'
)

function formatVal(v: number) {
  if (mode.value === 'km') return v.toFixed(1) + ' km'
  // 分钟 → 小时/分钟
  if (v >= 60) return (v / 60).toFixed(1) + ' h'
  return v.toFixed(0) + ' min'
}

function totalLabel(data: SegmentStats) {
  if (mode.value === 'km') {
    const total = Object.values(data.mileage_by_type).reduce((s, v) => s + v.total_km, 0)
    return total.toFixed(1) + ' km'
  }
  const total = Object.values(data.mileage_by_type).reduce((s, v) => s + v.total_min, 0)
  if (total >= 60) return (total / 60).toFixed(1) + ' h'
  return total.toFixed(0) + ' min'
}

function buildOption(data: SegmentStats) {
  const byType = data.mileage_by_type
  const pieData = Object.entries(byType).map(([k, v]) => ({
    name: STATE_LABELS[k] ?? k,
    value: mode.value === 'km' ? v.total_km : v.total_min,
    itemStyle: { color: STATE_COLORS[k] ?? '#999' },
  }))
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(5,20,60,.9)',
      borderColor: 'rgba(0,180,255,.3)',
      textStyle: { color: '#e0f0ff', fontSize: 12 },
      formatter: (p: { name: string; value: number; percent: number }) => {
        const formatted = formatVal(p.value)
        return `${p.name}: ${formatted} (${p.percent}%)`
      },
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

function refreshChart() {
  if (props.data && chart) {
    (chart as { setOption(o: unknown): void }).setOption(buildOption(props.data))
  }
}

async function initChart() {
  if (!chartRef.value) return
  const echarts = await import('echarts')
  chart = echarts.init(chartRef.value, null, { renderer: 'canvas' })
  if (props.data) (chart as { setOption(o: unknown): void }).setOption(buildOption(props.data))
}

watch(() => props.data, refreshChart)
watch(mode, refreshChart)

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
</script>

<template>
  <ScreenPanel :title="panelTitle">
    <template #header-extra>
      <div class="mode-toggle">
        <button :class="{ active: mode === 'km' }" @click="mode = 'km'">里程</button>
        <button :class="{ active: mode === 'min' }" @click="mode = 'min'">时长</button>
      </div>
    </template>

    <div class="chart-wrap">
      <div ref="chartRef" class="pie-chart" />
      <div v-if="data" class="center-label">
        <div class="cl-val">{{ totalLabel(data) }}</div>
        <div class="cl-sub">合计</div>
      </div>
    </div>
    <div v-if="data" class="legend-list">
      <div
        v-for="[k, v] in Object.entries(data.mileage_by_type)"
        :key="k"
        class="legend-row"
      >
        <span class="dot" :style="{ background: STATE_COLORS[k] ?? '#999' }" />
        <span class="lname">{{ STATE_LABELS[k] ?? k }}</span>
        <span class="lval">{{ formatVal(mode === 'km' ? v.total_km : v.total_min) }}</span>
        <span class="lcnt">{{ v.count }} 趟</span>
      </div>
    </div>
    <div v-else class="loading">加载中…</div>
  </ScreenPanel>
</template>

<style scoped>
.chart-wrap {
  height: 130px; flex-shrink: 0;
  position: relative;
  display: flex; align-items: center; justify-content: center;
}
.pie-chart { position: absolute; inset: 0; }

.center-label {
  position: relative; z-index: 1;
  text-align: center; pointer-events: none;
  line-height: 1.2;
}
.cl-val { font-size: 13px; font-weight: 700; color: #e0f4ff; }
.cl-sub { font-size: 10px; color: rgba(120,180,220,.5); }

/* ──── 切换按钮 ──── */
.mode-toggle {
  display: flex; gap: 2px;
  background: rgba(0,40,90,.5);
  border-radius: 4px; padding: 2px;
}
.mode-toggle button {
  font-size: 10px; padding: 1px 8px; border: none; border-radius: 3px;
  cursor: pointer; color: rgba(160,210,255,.6);
  background: transparent; transition: all .2s;
}
.mode-toggle button.active {
  background: rgba(0,180,255,.25);
  color: #7dd3fc;
}

.legend-list {
  overflow-y: auto; padding-top: 4px;
  scrollbar-width: thin; scrollbar-color: rgba(0,180,255,.2) transparent;
}
.legend-row {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 2px; font-size: 11px;
  border-bottom: 1px solid rgba(0,80,160,.15);
}
.dot   { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.lname { color: rgba(180,220,255,.85); flex: 1; white-space: nowrap; }
.lval  { color: #38bdf8; font-weight: 600; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.lcnt  { color: rgba(100,160,200,.5); min-width: 32px; text-align: right; flex-shrink: 0; }

.loading { color: rgba(100,160,200,.4); font-size: 12px; text-align: center; padding: 20px; }
</style>
