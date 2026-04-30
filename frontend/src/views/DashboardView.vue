<script setup lang="ts">
defineOptions({ name: 'DashboardView' })
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import { ElNotification } from 'element-plus'
import { useAmap } from '@/composables/useAmap'
import { useSSE } from '@/composables/useSSE'
import { useDashboardStore } from '@/stores/dashboard'
import { useAuthStore } from '@/stores/auth'
import VehicleStatusTag from '@/components/VehicleStatusTag.vue'
import EventTypeTag from '@/components/EventTypeTag.vue'
import type { VehiclePosition, AlertFrame, WorkState } from '@/types'
import { formatChinaDateTime } from '@/utils/datetime'

const dashboardStore = useDashboardStore()
const authStore = useAuthStore()

// Map — 中心点：恩施市
const { map, init: initMap, createMarker, setLayers } = useAmap('dashboard-map', {
  zoom: 14,
  center: [109.4753, 30.2832],
})

// Marker registry: vehicleId → marker
const markerMap = new Map<number, ReturnType<typeof createMarker>>()

// SSE connections（后端 Stage-7 就绪前 status 会停在 ERROR，不会无限重试）
const { lastMessage: locationFrame, status: locStatus, error: locError } = useSSE<VehiclePosition>('/api/stream/locations')
const { lastMessage: alertFrame, status: alertStatus } = useSSE<AlertFrame>('/api/stream/alerts')

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

// ─── Vehicle detail ───────────────────────────────────────────────────────────
const selectedVehicle = ref<VehiclePosition | null>(null)
const detailPanelVisible = ref(false)

// Work state → marker color
const STATE_COLORS: Record<WorkState, string> = {
  loading: '#fa8c16',
  unloading: '#52c41a',
  transport_loaded: '#f5222d',
  transport_empty: '#1890ff',
  unknown: '#8c8c8c',
}

function getMarkerContent(pos: VehiclePosition): string {
  const color = STATE_COLORS[pos.work_state] ?? '#8c8c8c'
  return `<div style="
    width:36px;height:36px;border-radius:50%;
    background:${color};border:3px solid #fff;
    display:flex;align-items:center;justify-content:center;
    color:#fff;font-size:12px;font-weight:700;
    box-shadow:0 2px 6px rgba(0,0,0,0.3);
    cursor:pointer;
  ">车</div>`
}

function updateOrCreateMarker(pos: VehiclePosition) {
  if (!map.value) return
  const key = pos.vehicle_id ?? pos.device_id
  const position: [number, number] = [pos.lng, pos.lat]

  let marker = markerMap.get(key)
  if (marker) {
    marker.setPosition(position)
  } else {
    // Use custom HTML content marker
    const m = createMarker(position, pos)
    m.on('click', () => {
      selectedVehicle.value = pos
      detailPanelVisible.value = true
    })
    markerMap.set(key, m)
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
  initMap()
})
</script>

<template>
  <div class="dashboard-page">
    <!-- SSE 状态提示（后端 Stage-7 未就绪时显示） -->
    <el-alert
      v-if="locStatus === 'ERROR'"
      :title="`实时推送暂不可用：${locError ?? 'SSE 接口未就绪（后端阶段 7 待开发）'}`"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 8px; flex-shrink: 0"
    />

    <!-- Top stat bar -->
    <div class="stat-bar">
      <div class="stat-item">
        <span class="stat-value">{{ dashboardStore.onlineCount }}</span>
        <span class="stat-label">在线车辆</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-value" style="color: #fa8c16">{{ stateStats.loading }}</span>
        <span class="stat-label">装料中</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" style="color: #52c41a">{{ stateStats.unloading }}</span>
        <span class="stat-label">卸料中</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" style="color: #f5222d">{{ stateStats.transport_loaded }}</span>
        <span class="stat-label">重载运输</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" style="color: #1890ff">{{ stateStats.transport_empty }}</span>
        <span class="stat-label">空载运输</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-value" style="color: #f5222d">{{ dashboardStore.alerts.length }}</span>
        <span class="stat-label">今日告警</span>
      </div>
    </div>

    <!-- Main content -->
    <div class="main-content">
      <!-- Map -->
      <div class="map-wrapper">
        <div id="dashboard-map" class="amap-container" />

        <!-- Layer switcher -->
        <div class="layer-switcher">
          <button
            v-for="opt in LAYER_OPTIONS"
            :key="opt.key"
            class="layer-btn"
            :class="{ active: activeLayer === opt.key }"
            @click="switchLayer(opt.key)"
          >
            <span class="layer-icon">{{ opt.icon }}</span>
            <span class="layer-label">{{ opt.label }}</span>
          </button>
        </div>

        <!-- Legend -->
        <div class="map-legend">
          <div
            v-for="(color, state) in STATE_COLORS"
            :key="state"
            class="legend-item"
          >
            <span class="legend-dot" :style="{ background: color }" />
            <VehicleStatusTag :state="(state as WorkState)" />
          </div>
        </div>
      </div>

      <!-- Side panel: vehicle list + alert log -->
      <div class="side-panel">
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
              <div v-if="!dashboardStore.positionList.length" class="empty-hint">
                暂无在线车辆
              </div>
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
              <div v-if="!dashboardStore.alerts.length" class="empty-hint">
                暂无告警记录
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <!-- Vehicle detail drawer -->
    <el-drawer
      v-model="detailPanelVisible"
      title="车辆详情"
      size="320px"
      :append-to-body="false"
    >
      <template v-if="selectedVehicle">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="车牌">
            {{ selectedVehicle.license_plate ?? `设备 ${selectedVehicle.device_id}` }}
          </el-descriptions-item>
          <el-descriptions-item label="作业状态">
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
          <el-descriptions-item label="最后更新">
            {{ formatChinaDateTime(selectedVehicle.recorded_at) }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: calc(100vh - 116px);
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

/* Layer switcher – top right corner of map */
.layer-switcher {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  gap: 6px;
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

.layer-btn:hover {
  background: rgba(255, 255, 255, 0.98);
  border-color: #409eff;
}

.layer-btn.active {
  background: #409eff;
  border-color: #409eff;
  color: #fff;
}

.layer-icon {
  font-size: 16px;
}

.layer-label {
  font-size: 11px;
  white-space: nowrap;
}

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
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
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
.vehicle-item.selected {
  background: #e6f4ff;
}

.vehicle-plate {
  font-weight: 600;
  font-size: 14px;
  color: #1d2129;
}

.vehicle-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.speed-text {
  font-size: 12px;
  color: #86909c;
}

.alert-item {
  padding: 10px 8px;
  border-bottom: 1px solid #f0f0f0;
}

.alert-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.alert-time {
  font-size: 11px;
  color: #86909c;
}

.alert-body {
  font-size: 13px;
  color: #555;
}

.empty-hint {
  padding: 24px;
  text-align: center;
  color: #86909c;
  font-size: 14px;
}
</style>
