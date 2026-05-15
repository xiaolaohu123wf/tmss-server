<!--
  大屏中央地图：
  - 地图中心与后台系统设置对齐（/api/admin/map-config）
  - 叠加正射影像瓦片（/static/map/orthophoto_amap_meta.json，可选）
  - 接入 SSE location 事件实时更新车辆位置标记
  - 点击车辆展示近1小时轨迹线
  - 标记颜色区分在线/工作状态
-->
<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useSSE } from '@/composables/useSSE'
import { get } from '@/api/index'
import type { VehiclePosition } from '@/types'

// AMap 类型声明
declare const AMap: {
  Map: new (el: HTMLElement, opts: Record<string, unknown>) => AMapInst
  Marker: new (opts: Record<string, unknown>) => AMapMarkerInst
  Polyline: new (opts: Record<string, unknown>) => AMapPolyInst
  Polygon: new (opts: Record<string, unknown>) => unknown
  TileLayer: {
    new (opts: Record<string, unknown>): AMapTileLayerInst
    Satellite: new (opts?: Record<string, unknown>) => AMapTileLayerInst
    RoadNet: new (opts?: Record<string, unknown>) => AMapTileLayerInst
  }
  Icon: new (opts: Record<string, unknown>) => unknown
}

interface AMapTileLayerInst {
  show(): void
  hide(): void
  setOpacity(v: number): void
}

interface AMapInst {
  add(o: unknown): void
  remove(o: unknown): void
  destroy(): void
  setFitView(overlays: unknown[], immediately?: boolean, avoid?: number[] | null, max?: number): void
  setZoomAndCenter(zoom: number, center: [number, number], immediately?: boolean): void
  clearMap(): void
  setMapStyle(style: string): void
  setLayers(layers: AMapTileLayerInst[]): void
}
interface AMapMarkerInst {
  setPosition(pos: [number, number]): void
  getPosition(): { lng: number; lat: number } | null
  setMap(m: AMapInst | null): void
  setContent(html: string): void
  on(ev: string, fn: () => void): void
}
interface AMapPolyInst {
  setPath(p: [number, number][]): void
  setMap(m: AMapInst | null): void
}

// ── 状态色映射 ──────────────────────────────────────────────
const STATE_COLOR: Record<string, string> = {
  transport_loaded: '#38bdf8',
  transport_empty:  '#818cf8',
  loading:          '#34d399',
  unloading:        '#fb923c',
  unknown:          '#9ca3af',
  idle:             '#6b7280',
}

const LARGE_STATES = new Set(['transport_loaded', 'transport_empty'])

function markerHtml(plate: string, state: string, online: boolean) {
  const color = online ? (STATE_COLOR[state] ?? '#9ca3af') : '#6b7280'
  const large = LARGE_STATES.has(state) && online
  // 重载/空载图标放大 1.5 倍：点 18px，脉冲环 27px
  const dotStyle = large
    ? `background:${color};box-shadow:0 0 12px ${color};width:18px;height:18px`
    : `background:${color};box-shadow:0 0 8px ${color}`
  const pulseStyle = large
    ? `border-color:${color};width:27px;height:27px`
    : `border-color:${color}`
  const pulse = online ? `<span class="mp" style="${pulseStyle}"></span>` : ''
  return `
  <div class="sm-wrap">
    ${pulse}
    <div class="sm-dot" style="${dotStyle}"></div>
    <div class="sm-label">${plate}</div>
  </div>`
}

// ── 组件 ────────────────────────────────────────────────────
const emit = defineEmits<{
  (e: 'online-ids', ids: Set<number>): void
  (e: 'select-vehicle', vehicleId: number): void
  (e: 'clear-focus'): void
}>()

const props = defineProps<{ focusVehicleId?: number | null }>()

const mapEl = ref<HTMLElement | null>(null)
let map: AMapInst | null = null

// 底图选项
type BaseMapKey = 'satellite' | 'roadnet' | 'blue' | 'dark'
interface BaseMapOption { key: BaseMapKey; label: string; style: string; useSatellite: boolean }
const BASE_MAPS: BaseMapOption[] = [
  { key: 'satellite', label: '🛰️ 卫星',  style: 'amap://styles/dark',   useSatellite: true  },
  { key: 'roadnet',   label: '🗺️ 路网',   style: 'amap://styles/normal', useSatellite: false },
  { key: 'blue',      label: '💙 蓝色',   style: 'amap://styles/blue',   useSatellite: false },
  { key: 'dark',      label: '⬛ 暗黑',   style: 'amap://styles/dark',   useSatellite: false },
]

// 图层状态
const baseMap         = ref<BaseMapKey>('satellite')
const domLayerLoaded  = ref(false)
const showDom         = ref(true)
const showRoadNet     = ref(false)
const showFences      = ref(true)

let satelliteLayer: AMapTileLayerInst | null = null
let roadNetLayer:   AMapTileLayerInst | null = null
let domLayer:       AMapTileLayerInst | null = null
let fencePolygons:  unknown[] = []
let fenceLabels:    AMapMarkerInst[] = []

// WGS-84 → GCJ-02 坐标转换（用于围栏坐标修正，与后台一致）
function _transLat(x: number, y: number): number {
  let r = -100 + 2*x + 3*y + 0.2*y*y + 0.1*x*y + 0.2*Math.sqrt(Math.abs(x))
  r += (20*Math.sin(6*x*Math.PI) + 20*Math.sin(2*x*Math.PI)) * 2/3
  r += (20*Math.sin(y*Math.PI) + 40*Math.sin(y/3*Math.PI)) * 2/3
  r += (160*Math.sin(y/12*Math.PI) + 320*Math.sin(y*Math.PI/30)) * 2/3
  return r
}
function _transLng(x: number, y: number): number {
  let r = 300 + x + 2*y + 0.1*x*x + 0.1*x*y + 0.1*Math.sqrt(Math.abs(x))
  r += (20*Math.sin(6*x*Math.PI) + 20*Math.sin(2*x*Math.PI)) * 2/3
  r += (20*Math.sin(x*Math.PI) + 40*Math.sin(x/3*Math.PI)) * 2/3
  r += (150*Math.sin(x/12*Math.PI) + 300*Math.sin(x/30*Math.PI)) * 2/3
  return r
}
function wgs84ToGcj02(lng: number, lat: number): [number, number] {
  const inChina = 73.66 < lng && lng < 135.05 && 3.86 < lat && lat < 53.55
  if (!inChina) return [lng, lat]
  const a = 6378245.0; const ee = 0.00669342162296594323
  let dlat = _transLat(lng - 105, lat - 35)
  let dlng = _transLng(lng - 105, lat - 35)
  const rad = lat / 180 * Math.PI
  let magic = Math.sin(rad); magic = 1 - ee * magic * magic
  const sq = Math.sqrt(magic)
  dlat = dlat * 180 / (a * (1 - ee) / (magic * sq) * Math.PI)
  dlng = dlng * 180 / (a / sq * Math.cos(rad) * Math.PI)
  return [lng + dlng, lat + dlat]
}

// 围栏类型颜色
const ZONE_COLORS: Record<string, string> = {
  loading:       '#34d399',
  unloading:     '#fb923c',
  restricted:    '#f87171',
  sharp_curve:   '#fbbf24',
  single_bridge: '#a78bfa',
  speed_zone:    '#38bdf8',
}

// 初始视角（onMounted 时从后台读取并存储，退出轨迹视图时恢复）
let initCenter: [number, number] = [109.2695, 30.383164]
let initZoomLevel = 15

// vehicleId → marker
const markers = new Map<number, AMapMarkerInst>()
// vehicleId → last position
const positions = new Map<number, { lat: number; lng: number; state: string; plate: string }>()

// ── 轨迹动画状态 ─────────────────────────────────────────────
let trackLine: AMapPolyInst | null = null        // 保留旧引用，兼容 watch 里的清理
let trackLayers: AMapPolyInst[]   = []           // 三层发光折线
let trackHead:   AMapMarkerInst | null = null    // 滑行光头
let trackAnimFrame: number | null = null         // RAF id
let trackPath: [number, number][] = []           // 当前路径点
const loadingTrack = ref(false)
let currentTrackVehicleId: number | null = null  // 正在加载轨迹的车辆 ID，用于取消过期请求
const TRACK_APPEND_MIN_DELTA = 1e-7              // 约厘米级，过滤重复点抖动

function clearTrack() {
  if (trackAnimFrame !== null) { cancelAnimationFrame(trackAnimFrame); trackAnimFrame = null }
  trackLayers.forEach(l => l.setMap(null))
  trackLayers = []
  trackHead?.setMap(null); trackHead = null
  trackLine?.setMap(null); trackLine = null
  trackPath = []
}

function appendTrackPoint(point: [number, number]) {
  if (!trackPath.length || !trackLayers.length) return
  const last = trackPath[trackPath.length - 1]
  if (
    Math.abs(last[0] - point[0]) < TRACK_APPEND_MIN_DELTA
    && Math.abs(last[1] - point[1]) < TRACK_APPEND_MIN_DELTA
  ) return
  trackPath.push(point)
  trackLayers.forEach(layer => layer.setPath(trackPath))
}

/** 按 progress(0→1) 插值折线上的坐标 */
function interpPath(path: [number, number][], t: number): [number, number] {
  const n = path.length
  if (n === 0) return [0, 0]
  if (n === 1) return path[0]
  const idx = t * (n - 1)
  const i = Math.min(Math.floor(idx), n - 2)
  const f = idx - i
  return [
    path[i][0] + (path[i + 1][0] - path[i][0]) * f,
    path[i][1] + (path[i + 1][1] - path[i][1]) * f,
  ]
}

function startTrackAnim() {
  if (!trackHead || !map) return
  let progress = 0
  const SPEED = 0.0006   // 每帧前进比例，控制光头速度

  function tick() {
    progress = (progress + SPEED) % 1
    const pos = interpPath(trackPath, progress)
    trackHead!.setPosition(pos)
    trackAnimFrame = requestAnimationFrame(tick)
  }
  trackAnimFrame = requestAnimationFrame(tick)
}

// ── SSE ─────────────────────────────────────────────────────
const { lastMessage: locMsg } = useSSE<VehiclePosition>('/api/stream', 'location')

watch(locMsg, (msg) => {
  if (!msg || !map) return
  if (!msg.vehicle_id) return
  const id = msg.vehicle_id
  const plate = msg.license_plate ?? `#${id}`
  const state = msg.work_state ?? 'unknown'
  positions.set(id, { lat: msg.lat, lng: msg.lng, state, plate })

  let mk = markers.get(id)
  if (!mk) {
    mk = new AMap.Marker({
      position: [msg.lng, msg.lat],
      content: markerHtml(plate, state, true),
      offset: [-16, -16],
      map,
    })
    mk.on('click', () => {
      emit('select-vehicle', id)
    })
    markers.set(id, mk)
  } else {
    mk.setPosition([msg.lng, msg.lat])
    mk.setContent(markerHtml(plate, state, true))
  }

  // 聚焦车辆在轨迹视图中持续前进时，实时延展高亮轨迹
  if (props.focusVehicleId === id) {
    appendTrackPoint([msg.lng, msg.lat])
  }

  // 更新在线 ID
  emit('online-ids', new Set(markers.keys()))
})

// ── 点击车辆后加载近1小时轨迹（三层发光 + 动画光头） ──────────
async function loadTrack(vehicleId: number) {
  if (!map) return
  // 标记本次请求归属，后续 await 后若已切换车辆则丢弃结果
  currentTrackVehicleId = vehicleId
  loadingTrack.value = true
  clearTrack()

  try {
    const now = new Date()
    const from = new Date(now.getTime() - 60 * 60 * 1000).toISOString()
    const to   = now.toISOString()

    type PtItem = { lat: number; lng: number }
    type SegItem = {
      id: number
      segment_type?: string | null
      ended_at?: string | null
      buffer_min?: number
    }
    const segs = await get<SegItem[]>(
      `/track-segments?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&vehicle_id=${vehicleId}&show_idle=false&limit=50`
    )
    // 若在等待期间用户已切换至其他车辆，丢弃本次结果
    if (currentTrackVehicleId !== vehicleId) return
    if (!segs.length) return

    // 优先使用与实时状态一致的在途段，其次开放段，最后兜底最新段（segs[0]）
    const realtimeState = positions.get(vehicleId)?.state ?? null
    const transportSeg = (realtimeState === 'transport_loaded' || realtimeState === 'transport_empty')
      ? segs.find(s => s.segment_type === realtimeState)
      : null
    const openSeg = segs.find(s => !s.ended_at)
    const chosenSeg = transportSeg ?? openSeg ?? segs[0]
    const bufferMin = Math.max(0, Number(chosenSeg.buffer_min ?? 0))

    const pts = await get<PtItem[]>(
      `/track-segments/${chosenSeg.id}/points?limit=2000&buffer_min=${bufferMin}`
    )
    // 二次检查：points 请求也是异步的
    if (currentTrackVehicleId !== vehicleId) return

    const path: [number, number][] = pts.map(p => [p.lng, p.lat])
    if (!path.length) return

    trackPath = path

    // 层1：外辉光（宽且透明）
    const outerGlow = new AMap.Polyline({
      path,
      strokeColor: '#1a8cff',
      strokeWeight: 22,
      strokeOpacity: 0.11,
      lineJoin: 'round', lineCap: 'round',
      map,
    })
    // 层2：中辉光
    const midGlow = new AMap.Polyline({
      path,
      strokeColor: '#1eb8ff',
      strokeWeight: 10,
      strokeOpacity: 0.42,
      lineJoin: 'round', lineCap: 'round',
      map,
    })
    // 层3：亮芯线
    const core = new AMap.Polyline({
      path,
      strokeColor: '#7de8ff',
      strokeWeight: 4,
      strokeOpacity: 1,
      lineJoin: 'round', lineCap: 'round',
      map,
    })
    trackLayers = [outerGlow, midGlow, core]
    // 兼容旧 watch 清理逻辑
    trackLine = core

    // 动画光头（从路径起点出发）
    trackHead = new AMap.Marker({
      position: path[0],
      content: '<div class="track-head"></div>',
      anchor: 'center',
      zIndex: 200,
      map,
    })

    startTrackAnim()

    map.setFitView([core as unknown], false, [60, 60, 60, 60], 17)
  } finally {
    // 只有当前请求仍是最新请求时才关闭 loading 指示
    if (currentTrackVehicleId === vehicleId) {
      loadingTrack.value = false
    }
  }
}

watch(() => props.focusVehicleId, (id) => {
  if (id != null) {
    loadTrack(id)
  } else {
    currentTrackVehicleId = null
    clearTrack()
    // 退出轨迹视图：恢复初始视角
    map?.setZoomAndCenter(initZoomLevel, initCenter, false)
  }
})

// ── 初始化地图 ───────────────────────────────────────────────
onMounted(async () => {
  if (!mapEl.value || !window.AMap) return

  // 1. 读后台地图中心配置（与 DashboardView / GeoZonesView 保持一致）
  try {
    const cfg = await get<{ map_center_lng: number; map_center_lat: number; map_zoom: number }>('/admin/map-config')
    initCenter = [cfg.map_center_lng, cfg.map_center_lat]
    if (cfg.map_zoom) initZoomLevel = cfg.map_zoom
  } catch { /* 保持默认中心 */ }
  const [centerLng, centerLat] = initCenter
  const initZoom = initZoomLevel

  // 2. 读正射影像 meta（可选，404 时静默忽略）
  interface OrthoMeta {
    tileUrlSuffix: string
    tileFormat: string
    center_gcj_lnglat: [number, number]
    bounds_gcj_lnglat: { southwest: [number, number]; northeast: [number, number] }
  }
  let orthoMeta: OrthoMeta | null = null
  try {
    const r = await fetch('/static/map/orthophoto_amap_meta.json', { cache: 'no-store' })
    if (r.ok) orthoMeta = (await r.json()) as OrthoMeta
  } catch { /* 正射瓦片不存在，跳过 */ }

  // 初始视角统一由后台「系统设置」里的地图中心/缩放决定，正射层仅叠加瓦片

  // 3. 初始化高德地图（默认卫星 + 暗色风格）
  satelliteLayer = new AMap.TileLayer.Satellite({ zIndex: 2 })
  roadNetLayer   = new AMap.TileLayer.RoadNet({ zIndex: 3, opacity: 0.8 })
  map = new AMap.Map(mapEl.value, {
    zoom: initZoom,
    center: [centerLng, centerLat],
    mapStyle: 'amap://styles/dark',
    layers: [satelliteLayer],   // 路网层单独 add，方便独立控制
  })
  // 路网层默认不显示，add 后立即隐藏
  map.add(roadNetLayer)
  roadNetLayer.hide()

  // 4. 叠加正射影像层（与 orthophoto_amap_test.html 相同逻辑）
  if (orthoMeta) {
    const suffix = orthoMeta.tileUrlSuffix || '/static/map/tiles_dom'
    const fmt    = orthoMeta.tileFormat    || 'png'
    domLayer = new AMap.TileLayer({
      zIndex: 6,
      opacity: 0.9,
      getTileUrl(x: number, y: number, z: number) {
        return `${suffix}/${z}/${x}/${y}.${fmt}`
      },
    })
    map.add(domLayer)
    domLayerLoaded.value = true
  }

  // 5. 加载并渲染用户绘制的围栏（默认显示）
  try {
    interface ZoneItem { id: number; zone_type: string; coordinates: [number, number][]; is_enabled: boolean; name: string }
    const zones = await get<ZoneItem[]>('/geo-zones')
    for (const z of zones) {
      if (!z.is_enabled) continue
      const color = ZONE_COLORS[z.zone_type] ?? '#64748b'
      // 围栏坐标由 AMap 绘制存入，已是 GCJ-02，无需二次转换
      const poly = new AMap.Polygon({
        path: z.coordinates,
        fillColor: color,
        fillOpacity: 0.12,
        strokeColor: color,
        strokeWeight: 1.5,
        strokeOpacity: 0.7,
        zIndex: 4,
        map,
      })
      fencePolygons.push(poly)

      // 围栏名称标签（最高顶点正上方）
      const cx    = z.coordinates.reduce((s, p) => s + p[0], 0) / z.coordinates.length
      const maxLat = Math.max(...z.coordinates.map(p => p[1]))
      const label = new AMap.Marker({
        position: [cx, maxLat],
        content: `<div class="fence-label" style="color:${color}">${z.name}</div>`,
        anchor: 'bottom-center',
        offset: [0, -4],   // 标签底边与顶点间留 4px 间距
        zIndex: 5,
        map,
      })
      fenceLabels.push(label)
    }
  } catch { /* 围栏加载失败时静默 */ }

  // 6. 注入全局 marker CSS（一次性）
  const styleText = `
      .sm-wrap {
        position: relative;
        width: 32px;
        height: 32px;
      }
      .sm-dot  {
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        width: 12px;
        height: 12px;
        border-radius: 50%;
      }
      .sm-label {
        position: absolute;
        left: 50%;
        top: calc(100% - 2px);
        transform: translateX(-50%);
        font-size: 10px;
        color: #fff;
        white-space: nowrap;
        background: rgba(0,0,0,.55);
        border-radius: 3px;
        padding: 0 3px;
        text-align: center;
        backdrop-filter: blur(4px);
      }
      .mp {
        position: absolute;
        left: 50%;
        top: 50%;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        border: 2px solid;
        opacity: .4;
        transform: translate(-50%, -50%);
        animation: mp-pulse 1.8s ease-out infinite;
      }
      @keyframes mp-pulse {
        0%   { transform: translate(-50%, -50%) scale(0.6); opacity: .6; }
        100% { transform: translate(-50%, -50%) scale(1.8); opacity: 0; }
      }
    `
  const existed = document.getElementById('sm-style') as HTMLStyleElement | null
  if (existed) {
    existed.textContent = styleText
  } else {
    const s = document.createElement('style')
    s.id = 'sm-style'
    s.textContent = styleText
    document.head.appendChild(s)
  }
})

// ── 图层切换 ─────────────────────────────────────────────────
watch(baseMap, (key) => {
  if (!map) return
  const opt = BASE_MAPS.find(b => b.key === key)!
  map.setMapStyle(opt.style)
  if (opt.useSatellite) {
    satelliteLayer?.show()
  } else {
    satelliteLayer?.hide()
  }
})

watch(showRoadNet, (v) => v ? roadNetLayer?.show() : roadNetLayer?.hide())
watch(showDom,     (v) => v ? domLayer?.show()     : domLayer?.hide())
watch(showFences,  (v) => {
  const method = v ? 'show' : 'hide'
  for (const p of fencePolygons) {
    ;(p as { show(): void; hide(): void })[method]()
  }
  for (const lb of fenceLabels) {
    ;(lb as unknown as { show(): void; hide(): void })[method]()
  }
})

onUnmounted(() => {
  markers.forEach(mk => mk.setMap(null))
  markers.clear()
  clearTrack()
  fencePolygons = []
  fenceLabels.forEach(lb => lb.setMap(null))
  fenceLabels = []
  map?.destroy()
  map = null
})
</script>

<template>
  <div class="screen-map-root">
    <div ref="mapEl" class="amap-container" />

    <!-- 右上角：图层控制面板 + 退出轨迹视图按钮（同列纵向排列） -->
    <div class="right-controls">
    <div class="layer-panel">
      <!-- 底图切换 -->
      <div class="lp-title">底图</div>
      <div class="basemap-btns">
        <button
          v-for="opt in BASE_MAPS"
          :key="opt.key"
          :class="['bm-btn', baseMap === opt.key && 'active']"
          @click="baseMap = opt.key"
        >{{ opt.label }}</button>
      </div>

      <div class="lp-divider" />

      <!-- 叠加图层 -->
      <div class="lp-title">叠加</div>
      <label class="lp-row">
        <input v-model="showRoadNet" type="checkbox" />
        路网标记
      </label>
      <label v-if="domLayerLoaded" class="lp-row">
        <input v-model="showDom" type="checkbox" />
        正射影像
      </label>
      <label class="lp-row">
        <input v-model="showFences" type="checkbox" />
        围栏
      </label>
    </div>

    <!-- 退出轨迹视图按钮（图层面板正下方） -->
    <Transition name="fade">
      <button
        v-if="focusVehicleId != null"
        class="clear-focus-btn"
        @click="emit('clear-focus')"
      >
        ✕ 退出轨迹视图
      </button>
    </Transition>
    </div><!-- end right-controls -->

    <!-- 图例 -->
    <div class="map-legend">
      <div v-for="[state, color] in Object.entries(STATE_COLOR).slice(0,5)" :key="state" class="legend-item">
        <span class="l-dot" :style="{ background: color }" />
        <span class="l-text">{{ ({ transport_loaded:'重载', transport_empty:'空载', loading:'装料', unloading:'卸料', unknown:'未知' } as Record<string,string>)[state] ?? state }}</span>
      </div>
    </div>

    <!-- 加载轨迹提示 -->
    <div v-if="loadingTrack" class="track-loading">轨迹加载中…</div>
  </div>
</template>

<style scoped>
.screen-map-root {
  position: relative;
  width: 100%; height: 100%;
}
.amap-container { width: 100%; height: 100%; }

.map-legend {
  position: absolute; bottom: 14px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 16px;
  background: rgba(0,10,30,.82); border: 1px solid rgba(0,180,255,.25);
  border-radius: 24px; padding: 7px 20px;
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 12px rgba(0,0,0,.4);
}
.legend-item { display: flex; align-items: center; gap: 6px; }
.l-dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; }
.l-text { font-size: 13px; color: rgba(200,230,255,.9); font-weight: 500; }

.right-controls {
  position: absolute; top: 10px; right: 10px; z-index: 10;
  display: flex; flex-direction: column; align-items: stretch; gap: 8px;
}

.layer-panel {
  background: rgba(0,8,28,.86);
  border: 1px solid rgba(0,180,255,.25);
  border-radius: 8px; padding: 8px 10px;
  backdrop-filter: blur(10px);
  min-width: 130px;
  box-shadow: 0 2px 12px rgba(0,0,0,.5);
}

.clear-focus-btn {
  font-size: 12px; color: #00d4ff;
  background: rgba(0,20,60,.85);
  border: 1px solid rgba(0,212,255,.35); border-radius: 8px;
  padding: 6px 10px; cursor: pointer;
  transition: all .2s; text-align: center;
  backdrop-filter: blur(10px);
  box-shadow: 0 2px 12px rgba(0,0,0,.5);
}
.clear-focus-btn:hover { background: rgba(0,40,100,.9); }

.fade-enter-active, .fade-leave-active { transition: opacity .25s; }
.fade-enter-from, .fade-leave-to       { opacity: 0; }
.lp-title {
  font-size: 10px; color: rgba(0,212,255,.45);
  text-transform: uppercase; letter-spacing: .08em;
  margin-bottom: 5px;
}
.lp-divider {
  height: 1px; background: rgba(0,180,255,.12);
  margin: 7px 0;
}
.basemap-btns {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 4px; margin-bottom: 2px;
}
.bm-btn {
  font-size: 11px; color: rgba(150,200,240,.65);
  background: rgba(0,30,80,.4);
  border: 1px solid rgba(0,180,255,.15);
  border-radius: 4px; padding: 4px 2px;
  cursor: pointer; text-align: center;
  transition: all .15s; white-space: nowrap;
}
.bm-btn:hover { border-color: rgba(0,180,255,.4); color: rgba(180,220,255,.9); }
.bm-btn.active {
  background: rgba(0,100,200,.3);
  border-color: rgba(0,212,255,.6);
  color: #00d4ff; font-weight: 600;
}
.lp-row {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; color: rgba(180,220,255,.75);
  cursor: pointer; padding: 2px 0;
  user-select: none;
}
.lp-row input { accent-color: #00d4ff; cursor: pointer; }

/* 围栏名称标签（与图例字号一致） */
:global(.fence-label) {
  font-size: 13px;
  font-weight: 600;
  text-shadow:
    0 0 6px rgba(0,0,0,.9),
    0 1px 3px rgba(0,0,0,.8);
  white-space: nowrap;
  pointer-events: none;
  letter-spacing: .5px;
}

.track-loading {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
  background: rgba(0,20,60,.85); border: 1px solid rgba(0,180,255,.3);
  color: #00d4ff; font-size: 13px; padding: 8px 20px; border-radius: 20px;
}

/* 轨迹动画光头（尺寸约为原设计的 0.5 倍） */
:global(.track-head) {
  width: 7px; height: 7px; border-radius: 50%;
  background: #fff;
  box-shadow:
    0 0 3px  1.5px rgba(30, 200, 255, 0.9),
    0 0 7px  3px rgba(30, 160, 255, 0.6),
    0 0 14px 6px rgba(0, 100, 255, 0.25);
  animation: th-pulse 1.2s ease-in-out infinite;
}
@keyframes th-pulse {
  0%, 100% { transform: scale(1);   opacity: 1; }
  50%       { transform: scale(1.2); opacity: 0.75; }
}
</style>
