<!-- 右侧面板1：运输趟次（近30天每日柱状图） -->
<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import ScreenPanel from './ScreenPanel.vue'
import type { SegmentStats } from '@/api/screen'

const props = defineProps<{ data: SegmentStats | null }>()
const chartRef = ref<HTMLElement | null>(null)
let chart: unknown = null

function buildOption(data: SegmentStats) {
  const days = data.daily_trips.map(d => d.day.slice(5))   // MM-DD
  const counts = data.daily_trips.map(d => d.count)
  const total = counts.reduce((s, c) => s + c, 0)

  return {
    backgroundColor: 'transparent',
    title: {
      text: `累计 ${total} 趟`,
      right: 8, top: 2,
      textStyle: { fontSize: 11, color: '#38bdf8', fontWeight: '600' },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(5,20,60,.9)',
      borderColor: 'rgba(0,180,255,.3)',
      textStyle: { color: '#e0f0ff', fontSize: 11 },
      formatter: (p: { dataIndex: number; value: number }[]) =>
        `${data.daily_trips[p[0].dataIndex]?.day ?? ''}<br/>趟次：${p[0].value}`,
    },
    grid: { left: 30, right: 12, top: 28, bottom: 24 },
    xAxis: {
      type: 'category',
      data: days,
      axisLabel: {
        color: 'rgba(150,200,240,.5)',
        fontSize: 9,
        interval: Math.floor(days.length / 6),
      },
      axisLine: { lineStyle: { color: 'rgba(0,180,255,.2)' } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: 'rgba(150,200,240,.5)', fontSize: 9 },
      splitLine: { lineStyle: { color: 'rgba(0,100,200,.15)' } },
    },
    series: [{
      type: 'bar',
      data: counts,
      barMaxWidth: 12,
      itemStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: '#38bdf8' },
            { offset: 1, color: 'rgba(56,189,248,.2)' },
          ],
        },
        borderRadius: [3, 3, 0, 0],
      },
      emphasis: { itemStyle: { color: '#00d4ff' } },
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
  <ScreenPanel title="运输趟次 · 近30天">
    <div class="chart-full">
      <div ref="chartRef" style="width:100%;height:100%" />
    </div>
  </ScreenPanel>
</template>

<style scoped>
.chart-full { width: 100%; height: 100%; }
</style>
