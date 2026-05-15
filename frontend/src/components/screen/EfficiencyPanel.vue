<!-- 右侧面板2：效率分析 -->
<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import ScreenPanel from './ScreenPanel.vue'
import DateRangePicker from './DateRangePicker.vue'
import type { EfficiencyStats } from '@/api/screen'

const props = defineProps<{ data: EfficiencyStats | null }>()
const chartRef = ref<HTMLElement | null>(null)
let chart: unknown = null

const METRICS = [
  { key: 'utilization_rate', label: '车辆开动率', unit: '%', color: '#34d399', max: 100 },
  { key: 'loaded_ratio',     label: '载重段占比', unit: '%', color: '#38bdf8', max: 100 },
] as const

function buildOption(data: EfficiencyStats) {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: 'rgba(5,20,60,.9)',
      borderColor: 'rgba(0,180,255,.3)',
      textStyle: { color: '#e0f0ff', fontSize: 11 },
    },
    grid: { left: 92, right: 46, top: 14, bottom: 20, containLabel: true },
    xAxis: {
      type: 'value', max: 100,
      axisLabel: { color: 'rgba(150,200,240,.5)', fontSize: 9, formatter: '{value}%' },
      axisLine: { lineStyle: { color: 'rgba(0,180,255,.2)' } },
      splitLine: { lineStyle: { color: 'rgba(0,100,200,.15)' } },
    },
    yAxis: {
      type: 'category',
      data: METRICS.map(m => m.label),
      axisLabel: { color: 'rgba(150,200,240,.7)', fontSize: 10 },
      axisLine: { show: false },
    },
    series: [{
      type: 'bar',
      data: METRICS.map(m => data[m.key]),
      barWidth: 14,
      label: {
        show: true, position: 'right', color: '#e0f0ff',
        fontSize: 11, formatter: '{c}%',
      },
      itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: (params: { dataIndex: number }) =>
          METRICS[params.dataIndex]?.color ?? '#38bdf8',
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
  <ScreenPanel title="效率分析">
    <template #header-extra>
      <DateRangePicker />
    </template>
    <div class="eff-wrap">
      <!-- 指标横条图 -->
      <div ref="chartRef" class="bar-chart" />

      <!-- 平均单趟时长 + 趟次汇总 -->
      <div v-if="data" class="metric-row-wrap">
        <div class="metric-card">
          <span class="mc-val">{{ data.avg_transport_min }}<small>min</small></span>
          <span class="mc-label">平均单趟运输时长</span>
        </div>
        <div class="metric-card">
          <span class="mc-val">{{ data.transport_trips }}</span>
          <span class="mc-label">运输往返总趟次</span>
        </div>
      </div>
    </div>
  </ScreenPanel>
</template>

<style scoped>
.eff-wrap { display: flex; flex-direction: column; height: 100%; gap: 6px; }
.bar-chart { flex: 1; min-height: 0; }
.metric-row-wrap {
  display: flex; gap: 6px; flex-shrink: 0;
}
.metric-card {
  flex: 1;
  background: rgba(0,30,80,.5);
  border: 1px solid rgba(0,180,255,.15);
  border-radius: 6px;
  display: flex; flex-direction: column; align-items: center;
  padding: 6px 4px;
}
.mc-val {
  font-size: 20px; font-weight: 700; color: #a78bfa;
  font-variant-numeric: tabular-nums;
}
.mc-val small { font-size: 11px; font-weight: 400; color: rgba(167,139,250,.6); margin-left: 2px; }
.mc-label { font-size: 10px; color: rgba(150,200,240,.6); margin-top: 1px; }
</style>
