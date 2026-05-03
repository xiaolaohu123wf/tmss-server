<script setup lang="ts">
defineOptions({ name: 'TracksView' })
import { ref, shallowRef, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import { useAmap } from '@/composables/useAmap'
import { formatChinaDateTime } from '@/utils/datetime'
import { tracksApi, type TrackSegment, type TrackPoint } from '@/api/tracks'
import { vehiclesApi } from '@/api/vehicles'
import { useAuthStore } from '@/stores/auth'
import type { Vehicle } from '@/types'

dayjs.extend(utc)

const authStore = useAuthStore()

/** 与渐进逆地理编码代数对齐：查询或切换行时作废旧任务，避免表格批量刷新抢主线程 */
let geocodeGeneration = 0

function bumpGeocodeGeneration(): void {
  geocodeGeneration += 1
}

function idleYield(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestIdleCallback !== 'undefined') {
      requestIdleCallback(() => resolve(), { timeout: 720 })
    } else {
      requestAnimationFrame(() => resolve())
    }
  })
}
interface TrackRow extends TrackSegment {
  start_place: string
  end_place: string
}

const loading = ref(false)
const pointsLoading = ref(false)
const tableRows = ref<TrackRow[]>([])
const vehicles = ref<Vehicle[]>([])
const vehicleFilter = ref<number | undefined>(undefined)
const dateRange = ref<[string, string]>([
  dayjs().subtract(7, 'day').startOf('day').format('YYYY-MM-DD HH:mm:ss'),
  dayjs().endOf('day').format('YYYY-MM-DD HH:mm:ss'),
])

const selectedId = ref<number | null>(null)
/** 大量轨迹点不做深度响应式，减轻播放/滑块时的 Vue 开销 */
const points = shallowRef<TrackPoint[]>([])
const playIndex = ref(0)
const playing = ref(false)
const playbackRate = ref(1)
let playTimer: ReturnType<typeof setTimeout> | null = null

/** 进度条下方文案用独立 ref，避免模板每次访问 points[playIndex] 触发大范围 diff */
const playbackMetaTime = ref('')
const playbackMetaSpeed = ref('—')

/** 轨迹加载结束后，右侧地图+播放区固定 300ms 显现（与 transition 一致） */
const TRACK_REVEAL_MS = 300
const trackStageRevealed = ref(true)

const { map, init, createPolyline, createMarker } = useAmap('tracks-map', {
  zoom: 13,
  center: [109.4753, 30.2832],
})

let polyline: ReturnType<typeof createPolyline> | null = null
let playMarker: ReturnType<typeof createMarker> | null = null
let geocoder: {
  getAddress: (
    lnglat: [number, number],
    cb: (status: string, result: { info: string; regeocode?: { formattedAddress?: string } }) => void,
  ) => void
} | null = null

type AMapGlobal = typeof window.AMap & {
  plugin: (mods: string[], cb: () => void) => void
  Geocoder: new (opts?: object) => {
    getAddress: (
      lnglat: [number, number],
      cb: (status: string, result: { info: string; regeocode?: { formattedAddress?: string } }) => void,
    ) => void
  }
}

function loadGeocoder(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!window.AMap) {
      reject(new Error('AMap not loaded'))
      return
    }
    const AM = window.AMap as AMapGlobal
    AM.plugin(['AMap.Geocoder'], () => {
      geocoder = new AM.Geocoder({ city: '全国' })
      resolve()
    })
  })
}

function reverseGeocode(lng: number, lat: number): Promise<string> {
  return new Promise((resolve) => {
    if (!geocoder) {
      resolve('—')
      return
    }
    geocoder.getAddress([lng, lat], (status, result) => {
      if (status === 'complete' && result.info === 'OK' && result.regeocode?.formattedAddress) {
        resolve(result.regeocode.formattedAddress)
      } else resolve('—')
    })
  })
}

async function enrichRowPlaces(r: TrackSegment): Promise<TrackRow> {
  let start_place = r.start_zone_name || '—'
  if (!r.start_zone_name && r.start_lat != null && r.start_lng != null) {
    start_place = await reverseGeocode(r.start_lng, r.start_lat)
  }
  let end_place = r.end_zone_name || '—'
  if (!r.end_zone_name && r.end_lat != null && r.end_lng != null) {
    end_place = await reverseGeocode(r.end_lng, r.end_lat)
  }
  return { ...r, start_place, end_place }
}

/** 地图折线抽稀：保持首尾与均匀采样，减少高德基线顶点数 */
const MAX_POLYLINE_VERTICES = 480

function lngLatPathForMap(pts: TrackPoint[]): [number, number][] {
  if (pts.length <= MAX_POLYLINE_VERTICES) {
    return pts.map((p) => [Number(p.lng), Number(p.lat)])
  }
  const out: [number, number][] = []
  const step = (pts.length - 1) / (MAX_POLYLINE_VERTICES - 1)
  for (let i = 0; i < MAX_POLYLINE_VERTICES - 1; i++) {
    const p = pts[Math.min(pts.length - 1, Math.round(i * step))]
    out.push([Number(p.lng), Number(p.lat)])
  }
  const last = pts[pts.length - 1]
  out.push([Number(last.lng), Number(last.lat)])
  return out
}

/** 在已有占位行上分批逆地理；代数不一致时立即停止，把主线程让给地图 */
async function runProgressiveGeocode(data: TrackSegment[], runId: number) {
  if (!data.length) return
  const rowMap = new Map<number, TrackRow>(tableRows.value.map((r) => [r.id, r]))
  const batch = 5
  for (let i = 0; i < data.length; i += batch) {
    if (runId !== geocodeGeneration) return
    const chunk = data.slice(i, i + batch)
    const done = await Promise.all(chunk.map((r) => enrichRowPlaces(r)))
    if (runId !== geocodeGeneration) return
    for (const row of done) rowMap.set(row.id, row)
    tableRows.value = data.map((r) => rowMap.get(r.id)!)
    await idleYield()
  }
}

async function fetchList() {
  loading.value = true
  bumpGeocodeGeneration()
  const geocodeRunId = geocodeGeneration
  let data: TrackSegment[] = []
  try {
    data = await tracksApi.list({
      from: dayjs(dateRange.value[0]).utc().format(),
      to: dayjs(dateRange.value[1]).utc().format(),
      vehicle_id: vehicleFilter.value,
      limit: 200,
    })
    await loadGeocoder().catch(() => {})
    selectedId.value = null
    clearTrackOverlays()
    points.value = []
    playbackMetaTime.value = ''
    playbackMetaSpeed.value = '—'
    trackStageRevealed.value = true
    tableRows.value = data.map((r) => ({
      ...r,
      start_place: r.start_zone_name || '—',
      end_place: r.end_zone_name || '—',
    }))
  } catch {
    ElMessage.error('加载轨迹列表失败')
    tableRows.value = []
  } finally {
    loading.value = false
  }
  if (data.length && geocodeRunId === geocodeGeneration) void runProgressiveGeocode(data, geocodeRunId)
}

function clearTrackOverlays() {
  polyline?.setMap(null)
  polyline = null
  playMarker?.setMap(null)
  playMarker = null
  playbackMetaTime.value = ''
  playbackMetaSpeed.value = '—'
}

async function onRowClick(row: TrackRow, _col: unknown, evt: Event) {
  // Element Plus 的 row-click 在点击子元素（按钮）时仍会触发；
  // 凡是命中 button / .el-button 的点击一律忽略，交由按钮自身的处理函数。
  if ((evt?.target as HTMLElement | null)?.closest('button, .el-button')) return

  bumpGeocodeGeneration()
  selectedId.value = row.id
  trackStageRevealed.value = false
  clearTrackOverlays()
  points.value = []
  pointsLoading.value = true
  playing.value = false
  stopPlayTimer()
  try {
    const raw = await tracksApi.points(row.id, 25000)
    // LBS 基站定位精度差，不参与轨迹回放
    const pts = raw.filter((p) => p.loc_type !== 'lbs')
    points.value = pts
    playIndex.value = 0
    await nextTick()
    drawTrack()
  } catch {
    ElMessage.error('加载轨迹点失败')
    points.value = []
    clearTrackOverlays()
  } finally {
    pointsLoading.value = false
  }
  await nextTick()
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      trackStageRevealed.value = true
    })
  })
}

async function handleDeleteSegment(row: TrackRow) {
  try {
    await ElMessageBox.confirm(
      `确认删除该轨迹段？车牌 ${row.license_plate ?? row.id}，下属定位点将一并删除且不可恢复。`,
      '删除轨迹',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
        lockScroll: false,
      },
    )
  } catch {
    return
  }
  try {
    await tracksApi.delete(row.id)
    ElMessage.success('已删除')
  } catch {
    return
  }
  bumpGeocodeGeneration()
  if (selectedId.value === row.id) {
    selectedId.value = null
    clearTrackOverlays()
    points.value = []
    playIndex.value = 0
    playing.value = false
    stopPlayTimer()
    trackStageRevealed.value = true
  }
  tableRows.value = tableRows.value.filter((r) => r.id !== row.id)
}

function drawTrack() {
  if (!map.value || points.value.length === 0) {
    clearTrackOverlays()
    return
  }
  clearTrackOverlays()
  const path = lngLatPathForMap(points.value)
  polyline = createPolyline(path, '#1890ff', 5)
  const p0 = points.value[0]
  playMarker = createMarker(
    [p0.lng, p0.lat],
    undefined,
    undefined,
  )
  playMarker.setLabel({
    content: '<span style="font-size:12px;font-weight:600">▶</span>',
    direction: 'top',
  })
  const pl = polyline
  const mk = playMarker
  requestAnimationFrame(() => {
    if (map.value && pl && mk) {
      // 第二参数 true：立即适配视野，禁用高德默认的飞入动画（否则常持续 1～3s）
      map.value.setFitView?.([pl as unknown as object, mk as unknown as object], true, null, 18)
    }
  })
  updateMarkerPos()
}

function updateMarkerPos() {
  if (!playMarker || !points.value.length) return
  const i = Math.min(Math.max(0, playIndex.value), points.value.length - 1)
  const p = points.value[i]
  playMarker.setPosition([p.lng, p.lat])
  playbackMetaTime.value = formatChinaDateTime(p.recorded_at)
  playbackMetaSpeed.value = p.speed != null ? String(p.speed) : '—'
}

const sliderMax = computed(() => Math.max(0, points.value.length - 1))

watch(playIndex, () => updateMarkerPos())

watch(playbackRate, () => {
  if (playing.value) {
    stopPlayTimer()
    startPlayTimer()
  }
})

function stopPlayTimer() {
  if (playTimer) {
    clearTimeout(playTimer)
    playTimer = null
  }
}

/**
 * 按真实时间轴回放：根据相邻两点的 recorded_at 差值确定等待时长，
 * 再除以 playbackRate 得到实际播放间隔。
 * 单帧最小 16ms（~60fps）；单帧最大 3000ms 避免长间隙卡顿。
 */
function scheduleNextFrame() {
  if (!playing.value || playIndex.value >= sliderMax.value) {
    if (playIndex.value >= sliderMax.value) playing.value = false
    return
  }

  const cur = points.value[playIndex.value]
  const next = points.value[playIndex.value + 1]

  let waitMs = 1000 / playbackRate.value   // 默认：假设 1s/点
  if (cur && next) {
    const realDiffMs = new Date(next.recorded_at).getTime() - new Date(cur.recorded_at).getTime()
    // 限幅：防止异常大间隙（段边界、断线恢复）造成长时间卡顿
    const clampedMs = Math.min(Math.max(realDiffMs, 0), 3000)
    waitMs = Math.max(16, clampedMs / playbackRate.value)
  }

  playTimer = setTimeout(() => {
    if (!playing.value) return
    playIndex.value = Math.min(playIndex.value + 1, sliderMax.value)
    scheduleNextFrame()
  }, waitMs)
}

function startPlayTimer() {
  stopPlayTimer()
  if (points.value.length < 2) return
  scheduleNextFrame()
}

watch(playing, (p) => {
  if (p) startPlayTimer()
  else stopPlayTimer()
})

function togglePlay() {
  if (!points.value.length) return
  if (playIndex.value >= sliderMax.value) playIndex.value = 0
  playing.value = !playing.value
}

onMounted(async () => {
  try {
    vehicles.value = await vehiclesApi.list()
  } catch {
    /* 无权限时列表可为空 */
  }
  await nextTick()
  init()
  await fetchList()
})

onUnmounted(() => {
  stopPlayTimer()
})
</script>

<template>
  <div class="tracks-page">
    <el-container class="tracks-wrap">
      <el-aside width="46%" class="tracks-aside">
        <div class="toolbar">
          <el-date-picker
            v-model="dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%; max-width: 380px"
          />
          <el-select
            v-model="vehicleFilter"
            placeholder="全部车辆"
            clearable
            filterable
            style="width: 160px"
          >
            <el-option
              v-for="v in vehicles"
              :key="v.id"
              :label="v.license_plate"
              :value="v.id"
            />
          </el-select>
          <el-button type="primary" :loading="loading" @click="fetchList">查询</el-button>
        </div>

        <el-table
          v-loading="loading"
          :data="tableRows"
          stripe
          height="calc(100vh - 220px)"
          highlight-current-row
          :row-key="(r: TrackRow) => r.id"
          :current-row-key="selectedId ?? undefined"
          @row-click="onRowClick"
        >
          <el-table-column prop="license_plate" label="车牌" width="100" />
          <el-table-column label="起止时间" min-width="170">
            <template #default="{ row }">
              <div class="cell-stack">
                <span>{{ formatChinaDateTime(row.started_at) }}</span>
                <template v-if="row.ended_at">
                  <span class="muted">至 {{ formatChinaDateTime(row.ended_at) }}</span>
                </template>
                <template v-else>
                  <el-tag type="success" size="small" effect="plain">进行中</el-tag>
                </template>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="距离(km)" width="88" align="right">
            <template #default="{ row }">
              {{ row.distance_km.toFixed(2) }}
            </template>
          </el-table-column>
          <el-table-column label="起点" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ row.start_place }}</template>
          </el-table-column>
          <el-table-column label="终点" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ row.end_place }}</template>
          </el-table-column>
          <el-table-column prop="cargo_name" label="货品" width="72">
            <template #default>—</template>
          </el-table-column>
          <el-table-column v-if="authStore.isManager" label="操作" width="72" fixed="right" align="center">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click.stop="() => handleDeleteSegment(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-aside>

      <el-main class="tracks-main">
        <div
          class="tracks-stage"
          v-loading="pointsLoading"
          element-loading-text="加载轨迹数据…"
          element-loading-background="rgba(255,255,255,0.88)"
        >
          <div
            class="tracks-stage-inner"
            :class="{ 'tracks-stage-inner--in': trackStageRevealed }"
            :style="{ transitionDuration: `${TRACK_REVEAL_MS}ms` }"
          >
            <div id="tracks-map" class="tracks-map" />
            <div class="playback-bar">
              <div class="pb-row">
                <el-button
                  type="primary"
                  :disabled="!points.length"
                  @click="togglePlay"
                >
                  {{ playing ? '暂停' : '播放' }}
                </el-button>
                <span class="pb-label">进度</span>
                <el-slider
                  v-model="playIndex"
                  :min="0"
                  :max="sliderMax || 0"
                  :disabled="!points.length"
                  :show-tooltip="false"
                  :format-tooltip="(v: number) => (points[v] ? formatChinaDateTime(points[v].recorded_at) : '')"
                  style="flex: 1; margin: 0 12px"
                />
                <span class="pb-label">倍速</span>
                <el-select v-model="playbackRate" style="width: 96px" :disabled="!points.length">
                  <el-option label="0.5×" :value="0.5" />
                  <el-option label="1×" :value="1" />
                  <el-option label="2×" :value="2" />
                  <el-option label="4×" :value="4" />
                  <el-option label="8×" :value="8" />
                  <el-option label="16×" :value="16" />
                  <el-option label="30×" :value="30" />
                  <el-option label="60×" :value="60" />
                  <el-option label="120×" :value="120" />
                </el-select>
              </div>
              <div v-if="points.length" class="pb-meta muted">
                点数 {{ points.length }} · 当前 {{ playIndex + 1 }} / {{ points.length }}
                <template v-if="playbackMetaTime">
                  · {{ playbackMetaTime }}
                  · 速度 {{ playbackMetaSpeed }} km/h
                </template>
              </div>
              <div v-else-if="selectedId" class="pb-meta muted">该段无轨迹点</div>
              <div v-else class="pb-meta muted">点击左侧表格一行加载轨迹</div>
            </div>
          </div>
        </div>
      </el-main>
    </el-container>
  </div>
</template>

<style scoped>
.tracks-page {
  height: 100%;
  min-height: 520px;
}
.tracks-wrap {
  height: calc(100vh - 120px);
  min-height: 480px;
}
.tracks-aside {
  display: flex;
  flex-direction: column;
  padding-right: 12px;
  border-right: 1px solid #e8e8e8;
  background: #fff;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}
.tracks-main {
  position: relative;
  padding: 0 !important;
  display: flex;
  flex-direction: column;
}
.tracks-stage {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 8px;
  overflow: hidden;
}
.tracks-stage-inner {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  opacity: 0;
  transition-property: opacity;
  transition-timing-function: ease;
}
.tracks-stage-inner--in {
  opacity: 1;
}
.tracks-map {
  flex: 1;
  min-height: 320px;
  border-radius: 8px;
  overflow: hidden;
}
.playback-bar {
  padding: 12px 16px;
  background: #fafafa;
  border-top: 1px solid #e8e8e8;
}
.pb-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.pb-label {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
}
.pb-meta {
  margin-top: 8px;
  font-size: 12px;
}
.muted {
  color: #8c8c8c;
  font-size: 12px;
}
.cell-stack {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.25;
}
</style>
