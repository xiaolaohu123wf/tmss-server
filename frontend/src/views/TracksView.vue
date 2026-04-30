<script setup lang="ts">
defineOptions({ name: 'TracksView' })
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import { useAmap } from '@/composables/useAmap'
import { formatChinaDateTime } from '@/utils/datetime'
import { tracksApi, type TrackSegment, type TrackPoint } from '@/api/tracks'
import { vehiclesApi } from '@/api/vehicles'
import type { Vehicle } from '@/types'

dayjs.extend(utc)

/** 列表行：展示用起止地点（围栏名或逆地理） */
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
const points = ref<TrackPoint[]>([])
const playIndex = ref(0)
const playing = ref(false)
const playbackRate = ref(1)
let playTimer: ReturnType<typeof setInterval> | null = null

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

async function enrichBatch(rows: TrackSegment[]): Promise<TrackRow[]> {
  const out: TrackRow[] = []
  const batch = 6
  for (let i = 0; i < rows.length; i += batch) {
    const chunk = rows.slice(i, i + batch)
    const done = await Promise.all(chunk.map((r) => enrichRowPlaces(r)))
    out.push(...done)
  }
  return out
}

async function fetchList() {
  loading.value = true
  try {
    const data = await tracksApi.list({
      from: dayjs(dateRange.value[0]).utc().format(),
      to: dayjs(dateRange.value[1]).utc().format(),
      vehicle_id: vehicleFilter.value,
      limit: 200,
    })
    await loadGeocoder().catch(() => {})
    tableRows.value = await enrichBatch(data)
    selectedId.value = null
    clearTrackOverlays()
    points.value = []
  } catch {
    ElMessage.error('加载轨迹列表失败')
  } finally {
    loading.value = false
  }
}

function clearTrackOverlays() {
  polyline?.setMap(null)
  polyline = null
  playMarker?.setMap(null)
  playMarker = null
}

async function onRowClick(row: TrackRow) {
  selectedId.value = row.id
  pointsLoading.value = true
  playing.value = false
  stopPlayTimer()
  try {
    const pts = await tracksApi.points(row.id, 25000)
    points.value = pts
    playIndex.value = 0
    await nextTick()
    drawTrack()
  } catch {
    ElMessage.error('加载轨迹点失败')
    points.value = []
  } finally {
    pointsLoading.value = false
  }
}

function drawTrack() {
  if (!map.value || points.value.length === 0) {
    clearTrackOverlays()
    return
  }
  clearTrackOverlays()
  const path: [number, number][] = points.value.map((p) => [p.lng, p.lat])
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
  map.value.setFitView?.([polyline as unknown as object, playMarker as unknown as object])
  updateMarkerPos()
}

function updateMarkerPos() {
  if (!playMarker || !points.value.length) return
  const i = Math.min(Math.max(0, playIndex.value), points.value.length - 1)
  const p = points.value[i]
  playMarker.setPosition([p.lng, p.lat])
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
    clearInterval(playTimer)
    playTimer = null
  }
}

function startPlayTimer() {
  stopPlayTimer()
  if (points.value.length < 2) return
  const base = 350
  const ms = Math.max(80, base / playbackRate.value)
  playTimer = setInterval(() => {
    if (playIndex.value >= sliderMax.value) {
      playing.value = false
      stopPlayTimer()
      return
    }
    playIndex.value++
  }, ms)
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
                <span class="muted">至 {{ row.ended_at ? formatChinaDateTime(row.ended_at) : '进行中' }}</span>
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
        </el-table>
      </el-aside>

      <el-main class="tracks-main">
        <div id="tracks-map" class="tracks-map" />
        <div class="playback-bar" v-loading="pointsLoading">
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
              :format-tooltip="(v: number) => (points[v] ? formatChinaDateTime(points[v].recorded_at) : '')"
              style="flex: 1; margin: 0 12px"
            />
            <span class="pb-label">倍速</span>
            <el-select v-model="playbackRate" style="width: 96px" :disabled="!points.length">
              <el-option label="0.5×" :value="0.5" />
              <el-option label="1×" :value="1" />
              <el-option label="2×" :value="2" />
              <el-option label="4×" :value="4" />
            </el-select>
          </div>
          <div v-if="points.length" class="pb-meta muted">
            点数 {{ points.length }} · 当前 {{ playIndex + 1 }} / {{ points.length }}
            <template v-if="points[playIndex]">
              · {{ formatChinaDateTime(points[playIndex].recorded_at) }}
              · 速度 {{ points[playIndex].speed ?? '—' }} km/h
            </template>
          </div>
          <div v-else-if="selectedId" class="pb-meta muted">该段无轨迹点</div>
          <div v-else class="pb-meta muted">点击左侧表格一行加载轨迹</div>
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
