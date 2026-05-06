<script setup lang="ts">
defineOptions({ name: 'DashboardView' })
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'

// ── 移动端检测 ─────────────────────────────────────────────
const isMobile = ref(window.innerWidth <= 768)
function _onResize() { isMobile.value = window.innerWidth <= 768 }
onMounted(() => window.addEventListener('resize', _onResize))
onUnmounted(() => window.removeEventListener('resize', _onResize))

// 手机端底部列表面板（null=关闭，'vehicles'=在线车辆，'alerts'=告警记录）
const mobileActivePanel = ref<'vehicles' | 'alerts' | null>(null)
import { ElNotification } from 'element-plus'
import { useAmap } from '@/composables/useAmap'
import { useSSE } from '@/composables/useSSE'
import { useDashboardStore } from '@/stores/dashboard'
import { useAuthStore } from '@/stores/auth'
import VehicleStatusTag from '@/components/VehicleStatusTag.vue'
import EventTypeTag from '@/components/EventTypeTag.vue'
import type { VehiclePosition, AlertFrame, WorkState } from '@/types'
import { formatChinaDateTime } from '@/utils/datetime'
import { get } from '@/api/index'
import { geoZonesApi } from '@/api/geoZones'
import type { GeoZone, Coordinate } from '@/types'
import type { AMapPolygon } from '@/composables/useAmap'

const dashboardStore = useDashboardStore()
const authStore = useAuthStore()

// 地图中心点初始值（等待后端返回后覆盖）
const mapCenter = ref<[number, number]>([109.4753, 30.2832])

const { map, init: initMap, setLayers, createPolygon } = useAmap('dashboard-map', {
  zoom: 14,
  center: mapCenter.value,
})

// ─── Marker + Trail registries ────────────────────────────────────────────────
const markerMap = new Map<number, unknown>()
// Track last work_state per vehicle — setContent() is expensive, skip if state unchanged
const markerWorkState = new Map<number, WorkState>()
// Track last rendered heading (degrees from north) per vehicle
const markerHeading = new Map<number, number | null>()
// Trail: vehicleId → last TRAIL_MAX [lng, lat] points
const TRAIL_MAX = 10
const trailPoints = new Map<number, [number, number][]>()
const trailPolylines = new Map<number, unknown>()

// RAF batching: collect updates within a single frame and flush together
let _rafPending = false
const _pendingUpdates = new Map<number, VehiclePosition>()

// SSE 连接 — 统一端点 /api/stream，按命名事件类型分别订阅
const { lastMessage: locationFrame, status: locStatus, error: locError } = useSSE<VehiclePosition>('/api/stream', 'location')
const { lastMessage: alertFrame, status: alertStatus } = useSSE<AlertFrame>('/api/stream', 'alert')

const sseReady = computed(() => locStatus.value === 'OPEN')

// ─── Layer switcher ──────────────────────────────────────────────────────────
type LayerKey = 'standard' | 'satellite' | 'satellite_road' | 'traffic'

const LAYER_OPTIONS: { key: LayerKey; label: string; icon: string }[] = [
  { key: 'standard',       label: '标准地图', icon: '🗺️' },
  { key: 'satellite',      label: '卫星图',   icon: '🛰️' },
  { key: 'satellite_road', label: '卫星+路网', icon: '🛣️' },
  { key: 'traffic',        label: '路况图',   icon: '🚦' },
]

const activeLayer = ref<LayerKey>('standard')

function switchLayer(key: LayerKey) {
  if (!window.AMap) return
  activeLayer.value = key
  switch (key) {
    case 'standard':
      setLayers([new window.AMap.TileLayer()])
      break
    case 'satellite':
      setLayers([new window.AMap.TileLayer.Satellite()])
      break
    case 'satellite_road':
      setLayers([
        new window.AMap.TileLayer.Satellite(),
        new window.AMap.TileLayer.RoadNet(),
      ])
      break
    case 'traffic':
      setLayers([
        new window.AMap.TileLayer(),
        new window.AMap.TileLayer.Traffic({ autoRefresh: true, interval: 180 }),
      ])
      break
  }
}

// ─── Geofence overlay ────────────────────────────────────────────────────────
const geoZoneOverlayOn = ref(false)
const geoZoneLoading = ref(false)
let geoZonePolygons: AMapPolygon[] = []

const ZONE_COLORS: Record<string, string> = {
  loading:       '#52c41a',
  unloading:     '#fa8c16',
  restricted:    '#f5222d',
  sharp_curve:   '#1890ff',
  single_bridge: '#595959',
  speed_zone:    '#722ed1',
}

function _clearZonePolygons() {
  for (const p of geoZonePolygons) {
    try { p.setMap(null) } catch { /* ignore */ }
  }
  geoZonePolygons = []
}

async function toggleGeoZoneOverlay() {
  if (geoZoneOverlayOn.value) {
    _clearZonePolygons()
    geoZoneOverlayOn.value = false
    return
  }
  geoZoneLoading.value = true
  try {
    const zones = await geoZonesApi.list()
    for (const zone of zones.filter((z) => z.is_enabled)) {
      const color = ZONE_COLORS[zone.zone_type] ?? '#1890ff'
      const poly = createPolygon(zone.coordinates as Coordinate[], zone, color, 0.15)
      geoZonePolygons.push(poly)
    }
    geoZoneOverlayOn.value = true
    if (!geoZonePolygons.length) ElNotification({ type: 'info', title: '暂无启用的电子围栏', duration: 2000 })
  } catch {
    ElNotification({ type: 'error', title: '围栏加载失败', duration: 2500 })
  } finally {
    geoZoneLoading.value = false
  }
}

// ─── Vehicle detail ───────────────────────────────────────────────────────────
const selectedVehicle = ref<VehiclePosition | null>(null)
const detailPanelVisible = ref(false)

// Work state → color for truck cab
const STATE_COLORS: Record<WorkState, string> = {
  loading: '#fa8c16',
  unloading: '#52c41a',
  transport_loaded: '#f5222d',
  transport_empty: '#1890ff',
  unknown: '#8c8c8c',
}

/**
 * 从 trail（最近 TRAIL_MAX 个 [lng, lat] 点）计算行驶方位角（北为 0°，顺时针）。
 * 取倒数第 1 点与倒数第 lookback+1 点之间的方位角，lookback 越大越平滑。
 * 若点数不足或位移太小则返回 null（保持上次方向）。
 */
function _computeHeading(trail: [number, number][]): number | null {
  if (trail.length < 2) return null
  const lookback = Math.min(trail.length - 1, 5)
  const [lng1, lat1] = trail[trail.length - 1 - lookback]
  const [lng2, lat2] = trail[trail.length - 1]
  const dLng = lng2 - lng1
  const dLat = lat2 - lat1
  // 忽略极小位移（设备静止或漂移），不更新方向
  if (dLng * dLng + dLat * dLat < 1e-12) return null
  const deg = Math.atan2(dLng, dLat) * (180 / Math.PI)
  return (deg + 360) % 360
}

/**
 * 判断两个 heading 角度之差是否超过阈值（考虑 0/360 折叠）。
 */
function _headingChanged(a: number | null, b: number | null, threshold = 8): boolean {
  if (a === null || b === null) return a !== b
  return Math.abs(((b - a + 540) % 360) - 180) > threshold
}

/**
 * 俯视（鸟瞰）卡车 SVG + 车牌标注。
 *
 * SVG 默认朝向：车头指向正北（↑），headingDeg = 0 → 不旋转，90 → 向东，以此类推。
 * 旋转量 = headingDeg（无需 -90 偏移），绕俯视图车身中心旋转，任何角度都视觉自然。
 *
 * 布局：车牌绝对定位在图标上方（不参与流式排版），marker anchor='center'
 * 使车身几何中心精确落在 GPS 坐标点。
 */
function makeTruckContent(pos: VehiclePosition, headingDeg: number | null): string {
  const color = STATE_COLORS[pos.work_state] ?? '#8c8c8c'
  const plate = pos.license_plate ?? `D${pos.device_id}`
  const rot = headingDeg !== null ? `transform:rotate(${headingDeg.toFixed(1)}deg);` : ''

  // 俯视卡车：车头（前风挡）在上（北），车尾在下，viewBox 24×34
  // 结构：车身矩形 + 前鼻尖 + 前风挡 + 四个车轮 + 厢货分隔线
  const svg = [
    `<svg width="24" height="34" viewBox="0 0 24 34" fill="none" xmlns="http://www.w3.org/2000/svg">`,
    // 车身主体
    `<rect x="3" y="4" width="18" height="28" rx="3" fill="${color}"/>`,
    // 前鼻尖（三角，指向北）
    `<path d="M 3 8 L 12 0 L 21 8 Z" fill="${color}"/>`,
    // 前风挡玻璃（浅蓝半透明）
    `<rect x="5" y="4" width="14" height="9" rx="1.5" fill="rgba(190,230,255,0.80)"/>`,
    // 驾驶室与货厢分隔线
    `<line x1="5" y1="15" x2="19" y2="15" stroke="rgba(0,0,0,0.18)" stroke-width="1.2"/>`,
    // 前轮（左 + 右）
    `<rect x="0" y="5" width="4" height="8" rx="1.5" fill="#2c2c2c"/>`,
    `<rect x="20" y="5" width="4" height="8" rx="1.5" fill="#2c2c2c"/>`,
    // 后轮（左 + 右）
    `<rect x="0" y="21" width="4" height="8" rx="1.5" fill="#2c2c2c"/>`,
    `<rect x="20" y="21" width="4" height="8" rx="1.5" fill="#2c2c2c"/>`,
    `</svg>`,
  ].join('')

  // 外层容器：position:relative，尺寸 = SVG 尺寸（24×34），用于 anchor:'center'
  // 车牌绝对定位在容器上方，不影响锚点计算
  return [
    `<div style="position:relative;width:24px;height:34px;cursor:pointer;`,
    `filter:drop-shadow(0 2px 5px rgba(0,0,0,.40))">`,
    // 车牌浮动在图标正上方
    `<div style="position:absolute;bottom:calc(100% + 4px);left:50%;`,
    `transform:translateX(-50%);`,
    `background:rgba(15,15,15,.80);color:#fff;font-size:11px;font-weight:700;`,
    `padding:1px 7px;border-radius:3px;white-space:nowrap;letter-spacing:.5px;`,
    `pointer-events:none">${plate}</div>`,
    // 俯视卡车（旋转）
    `<div style="${rot}width:24px;height:34px;transform-origin:center center">`,
    svg,
    `</div>`,
    `</div>`,
  ].join('')
}

/** 批量刷新待处理的 marker（RAF 回调中执行）*/
function _flushUpdates() {
  _rafPending = false
  if (!map.value || !window.AMap) { _pendingUpdates.clear(); return }

  for (const [key, pos] of _pendingUpdates) {
    const lngLat: [number, number] = [pos.lng, pos.lat]

    // ── 拖影数据 ──
    const trail = trailPoints.get(key) ?? []
    trail.push(lngLat)
    if (trail.length > TRAIL_MAX) trail.shift()
    trailPoints.set(key, trail)

    // ── 拖影折线 ──
    const polyline = trailPolylines.get(key) as { setPath(p: unknown): void } | undefined
    if (polyline) {
      polyline.setPath(trail)
    } else if (trail.length >= 2) {
      const pl = new window.AMap.Polyline({
        path: trail,
        strokeColor: '#1890ff',
        strokeOpacity: 0.55,
        strokeWeight: 4,
        strokeStyle: 'solid',
        lineJoin: 'round',
        lineCap: 'round',
        map: map.value,
      })
      trailPolylines.set(key, pl)
    }

    // ── 方向计算 ──
    const heading = _computeHeading(trail)

    // ── Marker ──
    const marker = markerMap.get(key) as {
      setPosition(p: [number, number]): void
      setContent(c: string): void
    } | undefined

    if (marker) {
      marker.setPosition(lngLat)
      // setContent() 昂贵（重建 DOM），只在作业状态或行驶方向变化时才调用
      const stateChanged = markerWorkState.get(key) !== pos.work_state
      const hdgChanged = _headingChanged(markerHeading.get(key) ?? null, heading)
      if (stateChanged || hdgChanged) {
        marker.setContent(makeTruckContent(pos, heading))
        markerWorkState.set(key, pos.work_state)
        markerHeading.set(key, heading)
      }
    } else {
      const m = new window.AMap.Marker({
        position: lngLat,
        content: makeTruckContent(pos, heading),
        anchor: 'center',
        map: map.value,
      })
      ;(m as { on(e: string, fn: () => void): void }).on('click', () => {
        selectedVehicle.value = pos
        detailPanelVisible.value = true
      })
      markerMap.set(key, m)
      markerWorkState.set(key, pos.work_state)
      markerHeading.set(key, heading)
    }
  }
  _pendingUpdates.clear()
}

/** 入队一帧更新，同一帧内同一车辆的多次更新只保留最新一条 */
function updateOrCreateMarker(pos: VehiclePosition) {
  const key = pos.vehicle_id ?? pos.device_id
  _pendingUpdates.set(key, pos)
  if (!_rafPending) {
    _rafPending = true
    requestAnimationFrame(_flushUpdates)
  }
}

// Handle incoming location frames
watch(locationFrame, (frame) => {
  if (!frame) return
  dashboardStore.updatePosition(frame)
  updateOrCreateMarker(frame)
})

// Handle incoming alert frames
watch(alertFrame, (frame) => {
  if (!frame) return
  dashboardStore.addAlert(frame)
  ElNotification({
    title: '告警',
    message: `${frame.license_plate ?? `设备${frame.device_id}`} — ${frame.message}`,
    type: 'warning',
    duration: 8000,
  })
})

// Stats
const stateStats = computed(() => {
  const counts: Record<WorkState, number> = {
    loading: 0,
    unloading: 0,
    transport_loaded: 0,
    transport_empty: 0,
    unknown: 0,
  }
  for (const pos of dashboardStore.positionList) {
    counts[pos.work_state] = (counts[pos.work_state] ?? 0) + 1
  }
  return counts
})

onMounted(async () => {
  await nextTick()
  // 从后端读取地图默认中心点，成功则覆盖初始值
  try {
    const cfg = await get<{ map_center_lng: number; map_center_lat: number }>('/admin/map-config')
    mapCenter.value = [cfg.map_center_lng, cfg.map_center_lat]
  } catch {
    // 读取失败保留硬编码默认值
  }
  initMap(mapCenter.value)
})

onUnmounted(() => {
  _rafPending = false
  _pendingUpdates.clear()
  markerWorkState.clear()
  markerHeading.clear()
  trailPoints.clear()
  trailPolylines.clear()
  markerMap.clear()
})
</script>

<template>
  <div class="dashboard-page" :class="{ 'dashboard-page--mobile': isMobile }">

    <!-- SSE 状态提示 -->
    <el-alert
      v-if="locStatus === 'ERROR'"
      :title="`实时推送暂不可用：${locError ?? 'SSE 接口未就绪'}`"
      type="warning"
      :closable="false"
      show-icon
      style="flex-shrink:0"
    />

    <!-- ══════════════════ 统计栏（PC + 手机共用）══════════════════ -->
    <div class="stat-bar">
      <div class="stat-item">
        <span class="stat-value">{{ dashboardStore.onlineCount }}</span>
        <span class="stat-label">在线</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-value" style="color:#fa8c16">{{ stateStats.loading }}</span>
        <span class="stat-label">装料</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" style="color:#52c41a">{{ stateStats.unloading }}</span>
        <span class="stat-label">卸料</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" style="color:#f5222d">{{ stateStats.transport_loaded }}</span>
        <span class="stat-label">重载</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" style="color:#1890ff">{{ stateStats.transport_empty }}</span>
        <span class="stat-label">空载</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-value" style="color:#f5222d">{{ dashboardStore.alerts.length }}</span>
        <span class="stat-label">告警</span>
      </div>
    </div>

    <!-- ══════════════════ 地图 + 图层切换 + 图例（共用）══════════════════ -->
    <div class="main-content">
      <div class="map-wrapper">
        <div id="dashboard-map" class="amap-container" />

        <!-- 图层切换 -->
        <div class="layer-switcher">
          <button
            v-for="opt in LAYER_OPTIONS"
            :key="opt.key"
            class="layer-btn"
            :class="{ active: activeLayer === opt.key }"
            @click="switchLayer(opt.key)"
          >
            <span class="layer-icon">{{ opt.icon }}</span>
            <span v-if="!isMobile" class="layer-label">{{ opt.label }}</span>
          </button>
        </div>

        <!-- 围栏叠加开关 -->
        <div class="fence-toggle">
          <button
            class="layer-btn"
            :class="{ active: geoZoneOverlayOn }"
            :disabled="geoZoneLoading"
            @click="toggleGeoZoneOverlay"
          >
            <span class="layer-icon">🔲</span>
            <span v-if="!isMobile" class="layer-label">
              {{ geoZoneLoading ? '加载…' : (geoZoneOverlayOn ? '隐藏围栏' : '显示围栏') }}
            </span>
          </button>
        </div>

        <!-- 图例：桌面纵向列表；手机为两列网格，图标 + 状态标签并列便于辨认 -->
        <div class="map-legend" :class="{ 'map-legend--mobile': isMobile }">
          <div class="legend-title">图例</div>
          <div
            v-for="(color, state) in STATE_COLORS"
            :key="state"
            class="legend-item"
          >
            <!-- 图例：缩略俯视卡车 (12×17 px) -->
            <svg width="12" height="17" viewBox="0 0 24 34" fill="none" aria-hidden="true">
              <rect x="3" y="4" width="18" height="28" rx="3" :fill="color"/>
              <path d="M 3 8 L 12 0 L 21 8 Z" :fill="color"/>
              <rect x="5" y="4" width="14" height="9" rx="1.5" fill="rgba(190,230,255,0.80)"/>
              <rect x="0" y="5" width="4" height="8" rx="1.5" fill="#2c2c2c"/>
              <rect x="20" y="5" width="4" height="8" rx="1.5" fill="#2c2c2c"/>
              <rect x="0" y="21" width="4" height="8" rx="1.5" fill="#2c2c2c"/>
              <rect x="20" y="21" width="4" height="8" rx="1.5" fill="#2c2c2c"/>
            </svg>
            <VehicleStatusTag :state="(state as WorkState)" />
          </div>
        </div>
      </div>

      <!-- ── PC 侧边面板（手机隐藏）─────────────────────────── -->
      <div v-if="!isMobile" class="side-panel">
        <el-tabs>
          <el-tab-pane label="在线车辆">
            <div class="vehicle-list">
              <div
                v-for="pos in dashboardStore.positionList"
                :key="pos.vehicle_id ?? pos.device_id"
                class="vehicle-item"
                :class="{ selected: selectedVehicle?.vehicle_id === pos.vehicle_id }"
                @click="() => { selectedVehicle = pos; detailPanelVisible = true }"
              >
                <div class="vehicle-plate">{{ pos.license_plate ?? `设备${pos.device_id}` }}</div>
                <div class="vehicle-meta">
                  <VehicleStatusTag :state="pos.work_state" />
                  <span class="speed-text">{{ pos.speed?.toFixed(1) ?? '0' }} km/h</span>
                </div>
              </div>
              <div v-if="!dashboardStore.positionList.length" class="empty-hint">暂无在线车辆</div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="告警记录">
            <div class="alert-list">
              <div
                v-for="(alert, idx) in dashboardStore.alerts"
                :key="idx"
                class="alert-item"
              >
                <div class="alert-header">
                  <EventTypeTag :type="alert.event_type" />
                  <span class="alert-time">{{ formatChinaDateTime(alert.created_at) }}</span>
                </div>
                <div class="alert-body">
                  {{ alert.license_plate ?? `设备${alert.device_id}` }} — {{ alert.message }}
                </div>
              </div>
              <div v-if="!dashboardStore.alerts.length" class="empty-hint">暂无告警记录</div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- ══════════════════ 手机端：可点击信息卡片 ══════════════════ -->
    <div v-if="isMobile" class="mobile-cards">
      <button class="mobile-card" @click="mobileActivePanel = 'vehicles'">
        <div class="mc-count">{{ dashboardStore.onlineCount }}</div>
        <div class="mc-label">
          <el-icon size="14"><Van /></el-icon>在线车辆
        </div>
        <el-icon class="mc-arrow" size="14"><ArrowRight /></el-icon>
      </button>
      <button class="mobile-card mobile-card--alert" @click="mobileActivePanel = 'alerts'">
        <div class="mc-count" style="color:#f5222d">{{ dashboardStore.alerts.length }}</div>
        <div class="mc-label">
          <el-icon size="14"><Bell /></el-icon>今日告警
        </div>
        <el-icon class="mc-arrow" size="14"><ArrowRight /></el-icon>
      </button>
    </div>

    <!-- ══════════════════ 车辆详情抽屉（PC + 手机共用）══════════════════ -->
    <el-drawer
      v-model="detailPanelVisible"
      title="车辆详情"
      :size="isMobile ? '60%' : '320px'"
      :direction="isMobile ? 'btt' : 'rtl'"
      :append-to-body="false"
    >
      <template v-if="selectedVehicle">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="车牌">
            {{ selectedVehicle.license_plate ?? `设备 ${selectedVehicle.device_id}` }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <VehicleStatusTag :state="selectedVehicle.work_state" />
          </el-descriptions-item>
          <el-descriptions-item label="速度">
            {{ selectedVehicle.speed?.toFixed(1) ?? '0' }} km/h
          </el-descriptions-item>
          <el-descriptions-item label="海拔">
            {{ selectedVehicle.altitude?.toFixed(1) ?? '—' }} m
          </el-descriptions-item>
          <el-descriptions-item label="经度">{{ selectedVehicle.lng }}</el-descriptions-item>
          <el-descriptions-item label="纬度">{{ selectedVehicle.lat }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatChinaDateTime(selectedVehicle.recorded_at) }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>

    <!-- ══════════════════ 手机端：底部列表抽屉 ══════════════════ -->
    <el-drawer
      v-if="isMobile"
      :model-value="mobileActivePanel !== null"
      :title="mobileActivePanel === 'vehicles' ? '在线车辆' : '告警记录'"
      direction="btt"
      size="55%"
      :append-to-body="true"
      @close="mobileActivePanel = null"
    >
      <!-- 在线车辆列表 -->
      <template v-if="mobileActivePanel === 'vehicles'">
        <div class="vehicle-list">
          <div
            v-for="pos in dashboardStore.positionList"
            :key="pos.vehicle_id ?? pos.device_id"
            class="vehicle-item"
            @click="() => { selectedVehicle = pos; detailPanelVisible = true; mobileActivePanel = null }"
          >
            <div class="vehicle-plate">{{ pos.license_plate ?? `设备${pos.device_id}` }}</div>
            <div class="vehicle-meta">
              <VehicleStatusTag :state="pos.work_state" />
              <span class="speed-text">{{ pos.speed?.toFixed(1) ?? '0' }} km/h</span>
            </div>
          </div>
          <div v-if="!dashboardStore.positionList.length" class="empty-hint">暂无在线车辆</div>
        </div>
      </template>

      <!-- 告警记录列表 -->
      <template v-if="mobileActivePanel === 'alerts'">
        <div class="alert-list">
          <div
            v-for="(alert, idx) in dashboardStore.alerts"
            :key="idx"
            class="alert-item"
          >
            <div class="alert-header">
              <EventTypeTag :type="alert.event_type" />
              <span class="alert-time">{{ formatChinaDateTime(alert.created_at) }}</span>
            </div>
            <div class="alert-body">
              {{ alert.license_plate ?? `设备${alert.device_id}` }} — {{ alert.message }}
            </div>
          </div>
          <div v-if="!dashboardStore.alerts.length" class="empty-hint">暂无告警记录</div>
        </div>
      </template>
    </el-drawer>

  </div>
</template>

<style scoped>
/* ══ PC 基础（不变）══════════════════════════════════════════ */
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: calc(100vh - 116px);
  padding: 0;
}

.stat-bar {
  background: #fff;
  border-radius: 8px;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 24px;
  flex-shrink: 0;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 60px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1d2129;
  line-height: 1;
}

.stat-label {
  font-size: 12px;
  color: #86909c;
  margin-top: 4px;
}

.stat-divider {
  width: 1px;
  height: 36px;
  background: #e8e8e8;
}

.main-content {
  display: flex;
  gap: 12px;
  flex: 1;
  overflow: hidden;
}

.map-wrapper {
  flex: 1;
  position: relative;
  border-radius: 8px;
  overflow: hidden;
}

.amap-container {
  width: 100%;
  height: 100%;
}

.layer-switcher {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  gap: 6px;
  z-index: 100;
}

.fence-toggle {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 100;
}

.layer-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 10px;
  border: 1.5px solid rgba(255, 255, 255, 0.85);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(4px);
  cursor: pointer;
  font-size: 11px;
  color: #303133;
  transition: all 0.18s;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  line-height: 1;
}

.layer-btn:hover { background: rgba(255, 255, 255, 0.98); border-color: #409eff; }
.layer-btn.active { background: #409eff; border-color: #409eff; color: #fff; }
.layer-icon { font-size: 16px; }
.layer-label { font-size: 11px; white-space: nowrap; }

.map-legend {
  position: absolute;
  bottom: 32px;
  left: 16px;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 6px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  backdrop-filter: blur(4px);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}

.legend-title {
  font-size: 11px;
  color: #909399;
  font-weight: 600;
  margin-bottom: 2px;
}

.legend-item { display: flex; align-items: center; gap: 8px; }

/* 手机图例：两列排版，五项完整展示图标 + el-tag 文案 */
.map-legend--mobile {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: flex-start;
  align-content: flex-start;
  max-width: min(360px, calc(100vw - 72px));
  padding: 8px 10px;
  gap: 8px 12px;
  bottom: 10px;
  left: 8px;
  right: auto;
}

.map-legend--mobile .legend-title {
  flex: 1 0 100%;
  margin-bottom: 4px;
  font-size: 12px;
  color: #606266;
}

.map-legend--mobile .legend-item {
  flex: 0 0 calc(50% - 6px);
  min-width: 0;
  gap: 6px;
}

.map-legend--mobile .legend-item :deep(.el-tag) {
  font-size: 12px;
  padding: 0 6px;
  height: 22px;
  line-height: 20px;
}

.side-panel {
  width: 320px;
  background: #fff;
  border-radius: 8px;
  padding: 0 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.vehicle-list,
.alert-list {
  overflow-y: auto;
  max-height: calc(100vh - 280px);
}

.vehicle-item {
  padding: 10px 8px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  border-radius: 4px;
}

.vehicle-item:hover,
.vehicle-item.selected { background: #e6f4ff; }

.vehicle-plate { font-weight: 600; font-size: 14px; color: #1d2129; }
.vehicle-meta { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.speed-text { font-size: 12px; color: #86909c; }

.alert-item { padding: 10px 8px; border-bottom: 1px solid #f0f0f0; }
.alert-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.alert-time { font-size: 11px; color: #86909c; }
.alert-body { font-size: 13px; color: #555; }

.empty-hint { padding: 24px; text-align: center; color: #86909c; font-size: 14px; }

/* ══ 手机端覆盖 ═══════════════════════════════════════════ */
.dashboard-page--mobile {
  /* 手机内容区无标签栏，仅减去顶栏 56px；用 dvh 适配浏览器地址栏 */
  height: calc(100dvh - 56px);
  gap: 0;
  overflow: hidden;
}

/* 手机统计栏：紧凑横向 */
.dashboard-page--mobile .stat-bar {
  padding: 8px 12px;
  gap: 0;
  border-radius: 0;
  border-bottom: 1px solid #f0f0f0;
  justify-content: space-around;
}

.dashboard-page--mobile .stat-item { min-width: 0; flex: 1; }

.dashboard-page--mobile .stat-value {
  font-size: 18px;
}

.dashboard-page--mobile .stat-label {
  font-size: 10px;
  margin-top: 2px;
}

.dashboard-page--mobile .stat-divider {
  height: 28px;
  flex-shrink: 0;
}

/* 手机地图区：flex:1 撑满剩余空间（stat-bar + mobile-cards 之外） */
.dashboard-page--mobile .main-content {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.dashboard-page--mobile .map-wrapper {
  border-radius: 0;
  width: 100%;
}

/* 图层切换按钮手机上只显示图标 */
.dashboard-page--mobile .layer-btn {
  padding: 5px 7px;
}

/* ══ 手机端快捷卡片 ══════════════════════════════════════ */
.mobile-cards {
  display: flex;
  gap: 0;
  flex-shrink: 0;
  border-top: 1px solid #e8e8e8;
  background: #fff;
}

.mobile-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: none;
  border: none;
  cursor: pointer;
  position: relative;
  -webkit-tap-highlight-color: transparent;
  border-right: 1px solid #f0f0f0;
}

.mobile-card:last-child { border-right: none; }
.mobile-card:active { background: #f5f5f5; }

.mc-count {
  font-size: 22px;
  font-weight: 700;
  color: #1890ff;
  line-height: 1;
  min-width: 28px;
}

.mc-label {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  font-size: 11px;
  color: #86909c;
}

.mc-label .el-icon { color: #1890ff; }
.mobile-card--alert .mc-label .el-icon { color: #f5222d; }

.mc-arrow {
  margin-left: auto;
  color: #c0c0c0;
}
</style>
