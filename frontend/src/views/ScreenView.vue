<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useScreenStore } from '@/stores/screen'

import SummaryPanel   from '@/components/screen/SummaryPanel.vue'
import FleetListPanel from '@/components/screen/FleetListPanel.vue'
import MileagePanel   from '@/components/screen/MileagePanel.vue'
import TripPanel      from '@/components/screen/TripPanel.vue'
import EfficiencyPanel from '@/components/screen/EfficiencyPanel.vue'
import AlarmPanel     from '@/components/screen/AlarmPanel.vue'
import ScreenMap      from '@/components/screen/ScreenMap.vue'
import type { Vehicle } from '@/types'

const router = useRouter()
const auth = useAuthStore()
const screen = useScreenStore()

// ── 时钟 ─────────────────────────────────────────────────────
const timeStr = ref('')
function tick() {
  const now = new Date()
  timeStr.value = now.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  })
}
let tickTimer: ReturnType<typeof setInterval>
let refreshTimer: ReturnType<typeof setInterval>

// ── 在线车辆 ─────────────────────────────────────────────────
const onlineIds = ref<Set<number>>(new Set())

// ── 点击车辆聚焦 ─────────────────────────────────────────────
const focusVehicleId = ref<number | null>(null)

function handleSelectVehicle(v: Vehicle) {
  focusVehicleId.value = v.id
}
function handleMapSelectVehicle(id: number) {
  focusVehicleId.value = focusVehicleId.value === id ? null : id
}

// ── 生命周期 ─────────────────────────────────────────────────
onMounted(async () => {
  tick()
  tickTimer = setInterval(tick, 1000)
  // 错误捕获：API 500 / 未登录时不让 mounted hook 崩溃
  try {
    await screen.fetchAll()
  } catch {
    // 数据面板保持 null 占位，不阻断地图
  }
  // 每5分钟刷新统计数据
  refreshTimer = setInterval(async () => {
    try { await screen.fetchAll() } catch { /* ignore */ }
  }, 5 * 60 * 1000)
})

onUnmounted(() => {
  clearInterval(tickTimer)
  clearInterval(refreshTimer)
})
</script>

<template>
  <div class="screen-root">
    <!-- ═══════════ 顶部标题栏 ═══════════ -->
    <header class="s-header">
      <div class="s-header-left">
        <span class="s-badge">实时监控</span>
      </div>
      <div class="s-header-center">
        <h1 class="s-title">姚家平水利枢纽 · 土方运输智能管控大屏</h1>
      </div>
      <div class="s-header-right">
        <span class="s-clock">{{ timeStr }}</span>
        <span class="s-user">{{ auth.session?.username }}</span>
        <button class="s-btn-admin" @click="router.push('/dashboard')">进入后台</button>
      </div>
    </header>

    <!-- ═══════════ 主内容区 ═══════════ -->
    <main class="s-body">

      <!-- ── 左侧面板列 ── -->
      <aside class="s-side s-left">
        <div class="left-slot left-summary">
          <SummaryPanel :data="screen.summary" />
        </div>
        <div class="left-slot left-fleet">
          <FleetListPanel
            :online-ids="onlineIds"
            @select-vehicle="handleSelectVehicle"
          />
        </div>
        <div class="left-slot left-mileage">
          <MileagePanel :data="screen.segmentStats" />
        </div>
      </aside>

      <!-- ── 中间地图 ── -->
      <section class="s-map-wrap">
        <ScreenMap
          :focus-vehicle-id="focusVehicleId"
          @online-ids="ids => { onlineIds = ids }"
          @select-vehicle="handleMapSelectVehicle"
          @clear-focus="focusVehicleId = null"
        />
      </section>

      <!-- ── 右侧面板列 ── -->
      <aside class="s-side s-right">
        <TripPanel       :data="screen.segmentStats" />
        <EfficiencyPanel :data="screen.efficiency" />
        <AlarmPanel      :data="screen.alarmStats" />
      </aside>

    </main>


  </div>
</template>

<style scoped>
/* ── 根容器 ──────────────────────────────────────────────────── */
.screen-root {
  width: 100vw; height: 100dvh;
  background: #050e1f;
  display: flex; flex-direction: column;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
  color: #e0f0ff;
  position: relative;
}


/* ── 顶部标题栏 ──────────────────────────────────────────────── */
.s-header {
  height: 52px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px;
  background: linear-gradient(180deg, rgba(0,60,120,.6) 0%, rgba(0,20,60,.8) 100%);
  border-bottom: 1px solid rgba(0,180,255,.2);
  box-shadow: 0 4px 20px rgba(0,0,0,.5);
  position: relative;
  z-index: 10;
}
.s-header::after {
  content: '';
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, #00d4ff, transparent);
}

.s-header-left { display: flex; align-items: center; gap: 10px; width: 240px; }
.s-header-center { flex: 1; text-align: center; }
.s-header-right {
  display: flex; align-items: center; gap: 12px;
  width: 240px; justify-content: flex-end;
}

.s-badge {
  font-size: 10px; color: #34d399;
  border: 1px solid rgba(52,211,153,.4); border-radius: 10px;
  padding: 2px 8px;
  animation: blink-badge 2s ease-in-out infinite;
}
@keyframes blink-badge {
  0%, 100% { opacity: 1; }
  50%       { opacity: .5; }
}

.s-title {
  font-size: 18px; font-weight: 700; color: #fff;
  letter-spacing: 2px; margin: 0;
  text-shadow: 0 0 20px rgba(0,212,255,.5);
}

.s-clock { font-size: 12px; color: rgba(0,212,255,.7); font-variant-numeric: tabular-nums; }
.s-user  { font-size: 12px; color: rgba(180,220,255,.6); }

.s-btn-admin {
  font-size: 12px; color: #00d4ff;
  background: rgba(0,212,255,.08);
  border: 1px solid rgba(0,212,255,.3); border-radius: 6px;
  padding: 4px 12px; cursor: pointer;
  transition: background .2s, box-shadow .2s;
}
.s-btn-admin:hover {
  background: rgba(0,212,255,.15);
  box-shadow: 0 0 12px rgba(0,212,255,.3);
}

/* ── 主内容区 ────────────────────────────────────────────────── */
.s-body {
  flex: 1; min-height: 0;
  display: grid;
  grid-template-columns: 260px 1fr 260px;
  gap: 8px;
  padding: 8px;
}

/* ── 侧边面板列 ──────────────────────────────────────────────── */
.s-side {
  display: flex; flex-direction: column; gap: 8px;
  min-height: 0; overflow: hidden;
}
/* 三个面板等分高度 */
.s-side > * { flex: 1; min-height: 0; }

/* 左侧高度比例：压缩运营概览，拉长运输里程 */
.left-slot { min-height: 0; display: flex; }
.left-slot > * { flex: 1; min-height: 0; }
.s-left .left-summary { flex: 0.84; }
.s-left .left-fleet   { flex: 1.08; }
.s-left .left-mileage { flex: 1.38; }

/* ── 地图区 ──────────────────────────────────────────────────── */
.s-map-wrap {
  position: relative;
  border: 1px solid rgba(0,180,255,.2);
  border-radius: 8px; overflow: hidden;
  box-shadow: 0 0 20px rgba(0,100,255,.15);
}


</style>

<!-- 大屏暗色日期选择器弹窗全局样式 -->
<style>
.screen-date-picker.el-picker__popper {
  background: rgba(2, 12, 40, 0.97) !important;
  border: 1px solid rgba(0, 180, 255, 0.3) !important;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.7) !important;
}
.screen-date-picker .el-date-range-picker__content,
.screen-date-picker .el-date-picker__header,
.screen-date-picker .el-picker-panel {
  background: transparent !important;
  color: #c8e8ff !important;
}
.screen-date-picker .el-date-table th,
.screen-date-picker .el-date-range-picker__header div {
  color: rgba(0, 212, 255, 0.7) !important;
}
.screen-date-picker .el-date-table td .el-date-table-cell__text {
  color: #c8e8ff !important;
}
.screen-date-picker .el-date-table td.disabled .el-date-table-cell__text {
  color: rgba(100, 140, 180, 0.3) !important;
  background: transparent !important;
}
.screen-date-picker .el-date-table td.in-range .el-date-table-cell {
  background: rgba(0, 100, 200, 0.25) !important;
}
.screen-date-picker .el-date-table td.start-date .el-date-table-cell,
.screen-date-picker .el-date-table td.end-date .el-date-table-cell {
  background: rgba(0, 180, 255, 0.35) !important;
  border-radius: 4px !important;
}
.screen-date-picker .el-date-table td:hover .el-date-table-cell {
  background: rgba(0, 150, 255, 0.2) !important;
}
.screen-date-picker .el-date-range-picker__header button,
.screen-date-picker .el-date-picker__header button {
  color: rgba(0, 212, 255, 0.7) !important;
}
.screen-date-picker .el-date-range-picker__header button:hover,
.screen-date-picker .el-date-picker__header button:hover {
  color: #00d4ff !important;
}
.screen-date-picker .el-picker-panel__footer {
  background: rgba(0, 10, 35, 0.95) !important;
  border-top: 1px solid rgba(0, 180, 255, 0.15) !important;
}
.screen-date-picker .el-picker-panel__footer .el-button {
  color: #00d4ff !important;
  border-color: rgba(0, 180, 255, 0.3) !important;
}
.screen-date-picker .el-date-range-picker__time-header {
  background: transparent !important;
  border-bottom: 1px solid rgba(0, 180, 255, 0.15) !important;
  color: #c8e8ff !important;
}
.screen-date-picker .el-date-range-picker .el-picker-panel__body {
  background: transparent !important;
}
</style>
