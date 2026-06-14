<script setup lang="ts">
defineOptions({ name: 'HistoryTasksView' })
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
import { tracksApi, type TrackSegment } from '@/api/tracks'
import { vehiclesApi } from '@/api/vehicles'
import { formatChinaDateTime } from '@/utils/datetime'
import type { Vehicle } from '@/types'

dayjs.extend(utc)
dayjs.extend(timezone)
const CN_TZ = 'Asia/Shanghai'

// ── 筛选状态 ───────────────────────────────────────────────
const vehicleFilter = ref<number | undefined>(undefined)
const dateRange = ref<[string, string]>([
  dayjs().subtract(6, 'day').startOf('day').format('YYYY-MM-DD HH:mm:ss'),
  dayjs().endOf('day').format('YYYY-MM-DD HH:mm:ss'),
])
const vehicles = ref<Vehicle[]>([])
const loading = ref(false)

// 运输段（只含 transport_loaded / transport_empty）
const segments = ref<TrackSegment[]>([])

onMounted(async () => {
  vehicles.value = await vehiclesApi.list()
  await doSearch()
})

async function doSearch() {
  loading.value = true
  try {
    const [from, to] = dateRange.value
    const raw = await tracksApi.list({
      from: dayjs.tz(from, CN_TZ).utc().toISOString(),
      to:   dayjs.tz(to,   CN_TZ).utc().toISOString(),
      vehicle_id: vehicleFilter.value,
      limit: 500,
      min_distance_km: 0,
      show_idle: false,
    })
    segments.value = raw.filter(
      (s) => s.segment_type === 'transport_loaded' || s.segment_type === 'transport_empty',
    )
  } catch {
    ElMessage.error('查询失败，请检查网络或参数')
  } finally {
    loading.value = false
  }
}

// ── 统计卡片 ────────────────────────────────────────────────
const stats = computed(() => {
  const segs = segments.value
  const loaded = segs.filter((s) => s.segment_type === 'transport_loaded')
  const empty  = segs.filter((s) => s.segment_type === 'transport_empty')
  const totalKm = segs.reduce((acc, s) => acc + s.distance_km, 0)
  const durations = segs.map((s) => {
    if (!s.ended_at) return 0
    return dayjs(s.ended_at).diff(dayjs(s.started_at), 'minute')
  }).filter((d) => d > 0)
  const avgMin = durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : 0
  return {
    total:     segs.length,
    loaded:    loaded.length,
    empty:     empty.length,
    totalKm:   totalKm.toFixed(1),
    avgMin,
  }
})

// ── 图表：分时段趟次 ────────────────────────────────────────
const chartBarRef = ref<HTMLElement | null>(null)
let chartBar: { setOption(o: unknown): void; resize(): void; dispose(): void } | null = null

function buildBarOption() {
  const segs = segments.value
  const [from, to] = dateRange.value
  const diffDays = dayjs(to).diff(dayjs(from), 'day')
  const groupByHour = diffDays <= 2

  // 生成时间桶
  const buckets: Map<string, number> = new Map()
  if (groupByHour) {
    // 按小时，0–23
    for (let h = 0; h < 24; h++) {
      buckets.set(`${String(h).padStart(2, '0')}:00`, 0)
    }
    for (const s of segs) {
      const h = dayjs.utc(s.started_at).tz(CN_TZ).format('HH') + ':00'
      buckets.set(h, (buckets.get(h) ?? 0) + 1)
    }
  } else {
    // 按天，从 from 到 to
    let cur = dayjs.tz(from, CN_TZ).startOf('day')
    const end = dayjs.tz(to, CN_TZ).startOf('day')
    while (cur.isBefore(end) || cur.isSame(end, 'day')) {
      buckets.set(cur.format('MM-DD'), 0)
      cur = cur.add(1, 'day')
    }
    for (const s of segs) {
      const d = dayjs.utc(s.started_at).tz(CN_TZ).format('MM-DD')
      if (buckets.has(d)) buckets.set(d, (buckets.get(d) ?? 0) + 1)
    }
  }

  const xData = [...buckets.keys()]
  const yData = [...buckets.values()]

  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 24, bottom: 36 },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: { rotate: xData.length > 14 ? 45 : 0, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { fontSize: 11 },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
    },
    series: [{
      type: 'bar',
      data: yData,
      barMaxWidth: 32,
      label: { show: true, position: 'top', fontSize: 11, formatter: (p: { value: number }) => p.value || '' },
      itemStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: '#1890ff' }, { offset: 1, color: '#bae0ff' }] },
        borderRadius: [3, 3, 0, 0],
      },
    }],
  }
}

async function initBarChart() {
  if (!chartBarRef.value) return
  const echarts = await import('echarts')
  chartBar = echarts.init(chartBarRef.value, null, { renderer: 'canvas' }) as typeof chartBar
  chartBar!.setOption(buildBarOption())
}

// ── 图表：重载 vs 空载饼图 ──────────────────────────────────
const chartPieRef = ref<HTMLElement | null>(null)
let chartPie: { setOption(o: unknown): void; resize(): void; dispose(): void } | null = null

function buildPieOption() {
  return {
    tooltip: { trigger: 'item', formatter: '{b}：{c} 次 ({d}%)' },
    legend: { bottom: 8, textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['40%', '68%'],
      center: ['50%', '44%'],
      data: [
        { value: stats.value.loaded, name: '重载运输', itemStyle: { color: '#1890ff' } },
        { value: stats.value.empty,  name: '空载运输',  itemStyle: { color: '#a0cfff' } },
      ],
      label: { formatter: '{b}\n{c}次', fontSize: 12 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,.3)' } },
    }],
  }
}

async function initPieChart() {
  if (!chartPieRef.value) return
  const echarts = await import('echarts')
  chartPie = echarts.init(chartPieRef.value, null, { renderer: 'canvas' }) as typeof chartPie
  chartPie!.setOption(buildPieOption())
}

// ── 图表：各车辆趟次横向柱 ─────────────────────────────────
const chartVehicleRef = ref<HTMLElement | null>(null)
let chartVehicle: { setOption(o: unknown): void; resize(): void; dispose(): void } | null = null

function buildVehicleOption() {
  // 按车辆汇总
  const map: Map<string, { loaded: number; empty: number }> = new Map()
  for (const s of segments.value) {
    const key = s.license_plate ?? `#${s.vehicle_id}`
    if (!map.has(key)) map.set(key, { loaded: 0, empty: 0 })
    const entry = map.get(key)!
    if (s.segment_type === 'transport_loaded') entry.loaded++
    else entry.empty++
  }
  const names   = [...map.keys()]
  const loaded  = names.map((n) => map.get(n)!.loaded)
  const empty   = names.map((n) => map.get(n)!.empty)

  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 4, textStyle: { fontSize: 11 } },
    grid: { left: 80, right: 16, top: 32, bottom: 8 },
    xAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 11 }, splitLine: { lineStyle: { color: '#f0f0f0' } } },
    yAxis: { type: 'category', data: names, axisLabel: { fontSize: 11 } },
    series: [
      {
        name: '重载运输',
        type: 'bar',
        data: loaded,
        stack: 'total',
        barMaxWidth: 20,
        itemStyle: { color: '#1890ff', borderRadius: [0, 0, 0, 0] },
        label: { show: true, fontSize: 10, formatter: (p: { value: number }) => p.value || '' },
      },
      {
        name: '空载运输',
        type: 'bar',
        data: empty,
        stack: 'total',
        barMaxWidth: 20,
        itemStyle: { color: '#a0cfff', borderRadius: [0, 3, 3, 0] },
        label: { show: true, fontSize: 10, formatter: (p: { value: number }) => p.value || '' },
      },
    ],
  }
}

async function initVehicleChart() {
  if (!chartVehicleRef.value) return
  const echarts = await import('echarts')
  chartVehicle = echarts.init(chartVehicleRef.value, null, { renderer: 'canvas' }) as typeof chartVehicle
  chartVehicle!.setOption(buildVehicleOption())
}

// 数据变化时刷新图表
watch(segments, async () => {
  await nextTick()
  chartBar?.setOption(buildBarOption())
  chartPie?.setOption(buildPieOption())
  chartVehicle?.setOption(buildVehicleOption())
})

const resizeObs = new ResizeObserver(() => {
  chartBar?.resize()
  chartPie?.resize()
  chartVehicle?.resize()
})

onMounted(async () => {
  await nextTick()
  await initBarChart()
  await initPieChart()
  await initVehicleChart()
  if (chartBarRef.value)     resizeObs.observe(chartBarRef.value)
  if (chartPieRef.value)     resizeObs.observe(chartPieRef.value)
  if (chartVehicleRef.value) resizeObs.observe(chartVehicleRef.value)
})

onUnmounted(() => {
  resizeObs.disconnect()
  chartBar?.dispose()
  chartPie?.dispose()
  chartVehicle?.dispose()
})

// ── 表格辅助 ────────────────────────────────────────────────
function durationMin(s: TrackSegment): number {
  if (!s.ended_at) return 0
  return Math.round(dayjs(s.ended_at).diff(dayjs(s.started_at), 'minute'))
}

const TYPE_META: Record<string, { label: string; type: 'primary' | 'info' }> = {
  transport_loaded: { label: '重载运输', type: 'primary' },
  transport_empty:  { label: '空载运输', type: 'info'    },
}

// ── CSV 导出 ────────────────────────────────────────────────
function exportCsv() {
  const header = ['车牌', '类型', '开始时间', '结束时间', '时长(分)', '里程(km)', '起点围栏', '终点围栏', '货物']
  const rows = segments.value.map((s) => [
    s.license_plate ?? '',
    TYPE_META[s.segment_type ?? '']?.label ?? s.segment_type ?? '',
    formatChinaDateTime(s.started_at),
    s.ended_at ? formatChinaDateTime(s.ended_at) : '',
    durationMin(s),
    s.distance_km.toFixed(2),
    s.start_zone_name ?? '',
    s.end_zone_name ?? '',
    s.cargo_name ?? '',
  ])
  const csv = [header, ...rows].map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `运输任务_${dayjs().format('YYYYMMDD_HHmmss')}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="history-tasks">

    <!-- ── 筛选栏 ─────────────────────────────────────────── -->
    <el-card class="filter-card" shadow="never">
      <el-form inline label-width="72px">
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="dateRange"
            type="datetimerange"
            value-format="YYYY-MM-DD HH:mm:ss"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            :default-time="[new Date(2000,0,1,0,0,0), new Date(2000,0,1,23,59,59)]"
            style="width: 360px"
          />
        </el-form-item>
        <el-form-item label="车辆">
          <el-select v-model="vehicleFilter" placeholder="全部车辆" clearable style="width: 160px">
            <el-option
              v-for="v in vehicles"
              :key="v.id"
              :label="v.license_plate || `车辆#${v.id}`"
              :value="v.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="doSearch">查询</el-button>
          <el-button @click="exportCsv" :disabled="!segments.length">导出 CSV</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ── 统计卡片 ─────────────────────────────────────────── -->
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="6">
        <div class="stat-card" style="--acc:#1890ff">
          <div class="stat-icon">🚛</div>
          <div class="stat-val">{{ stats.total }}</div>
          <div class="stat-label">运输总趟次</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card" style="--acc:#1890ff">
          <div class="stat-icon">📦</div>
          <div class="stat-val">{{ stats.loaded }}</div>
          <div class="stat-label">重载运输</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card" style="--acc:#69b1ff">
          <div class="stat-icon">🔃</div>
          <div class="stat-val">{{ stats.empty }}</div>
          <div class="stat-label">空载运输</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-card" style="--acc:#52c41a">
          <div class="stat-icon">📏</div>
          <div class="stat-val">{{ stats.totalKm }}</div>
          <div class="stat-label">总里程 (km)</div>
        </div>
      </el-col>
    </el-row>

    <!-- ── 图表区 ─────────────────────────────────────────── -->
    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :sm="16">
        <el-card shadow="never" class="chart-card">
          <template #header>
            <span class="chart-title">分时段运输趟次</span>
            <span class="chart-subtitle">（≤2天按小时统计，否则按天）</span>
          </template>
          <div ref="chartBarRef" class="chart-box" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="chart-title">重载 / 空载占比</span></template>
          <div ref="chartPieRef" class="chart-box" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row" v-if="!vehicleFilter">
      <el-col :span="24">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="chart-title">各车辆运输趟次</span></template>
          <div
            ref="chartVehicleRef"
            :style="{ height: Math.max(180, segments.length ? 60 + new Set(segments.map(s => s.license_plate)).size * 36 : 180) + 'px' }"
            style="width:100%"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- ── 数据表格 ─────────────────────────────────────────── -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <span>运输记录明细</span>
        <span class="table-count">共 {{ segments.length }} 条</span>
      </template>

      <el-table
        :data="segments"
        v-loading="loading"
        stripe
        size="small"
        style="width:100%"
        :max-height="480"
      >
        <el-table-column label="车牌" prop="license_plate" min-width="90" fixed>
          <template #default="{ row }">{{ row.license_plate || `#${row.vehicle_id}` }}</template>
        </el-table-column>

        <el-table-column label="类型" width="96">
          <template #default="{ row }">
            <el-tag :type="TYPE_META[row.segment_type]?.type ?? 'info'" size="small">
              {{ TYPE_META[row.segment_type]?.label ?? row.segment_type }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="开始时间" min-width="148">
          <template #default="{ row }">{{ formatChinaDateTime(row.started_at) }}</template>
        </el-table-column>

        <el-table-column label="结束时间" min-width="148">
          <template #default="{ row }">{{ row.ended_at ? formatChinaDateTime(row.ended_at) : '—' }}</template>
        </el-table-column>

        <el-table-column label="时长(分)" width="76" align="right">
          <template #default="{ row }">{{ row.ended_at ? durationMin(row) : '—' }}</template>
        </el-table-column>

        <el-table-column label="里程(km)" prop="distance_km" width="80" align="right">
          <template #default="{ row }">{{ row.distance_km.toFixed(2) }}</template>
        </el-table-column>

        <el-table-column label="起点围栏" prop="start_zone_name" min-width="100">
          <template #default="{ row }">{{ row.start_zone_name || '—' }}</template>
        </el-table-column>

        <el-table-column label="终点围栏" prop="end_zone_name" min-width="100">
          <template #default="{ row }">{{ row.end_zone_name || '—' }}</template>
        </el-table-column>

        <el-table-column label="货物" prop="cargo_name" min-width="80">
          <template #default="{ row }">{{ row.cargo_name || '—' }}</template>
        </el-table-column>
      </el-table>
    </el-card>

  </div>
</template>

<style scoped>
.history-tasks {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── 筛选栏 ── */
.filter-card :deep(.el-card__body) { padding: 16px 20px 4px; }

/* ── 统计卡片 ── */
.stat-row { margin: 0; }
.stat-card {
  background: #fff;
  border-radius: 8px;
  border-top: 3px solid var(--acc);
  padding: 18px 16px 14px;
  text-align: center;
  box-shadow: 0 1px 4px rgba(0,0,0,.08);
  margin-bottom: 0;
}
.stat-icon  { font-size: 22px; margin-bottom: 4px; }
.stat-val   { font-size: 26px; font-weight: 700; color: var(--acc); line-height: 1.2; }
.stat-label { font-size: 12px; color: #888; margin-top: 4px; }

/* ── 图表 ── */
.chart-row  { margin: 0; }
.chart-card :deep(.el-card__body) { padding: 12px 16px; }
.chart-card :deep(.el-card__header) { padding: 12px 16px; }
.chart-title   { font-size: 14px; font-weight: 600; color: #333; }
.chart-subtitle { font-size: 11px; color: #aaa; margin-left: 6px; }
.chart-box     { width: 100%; height: 220px; }

/* ── 表格 ── */
.table-card :deep(.el-card__header) {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 600;
}
.table-count { font-size: 12px; color: #888; font-weight: normal; }
</style>
