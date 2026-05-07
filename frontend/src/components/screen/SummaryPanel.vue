<!-- 左侧面板1：车辆/车队/用户/在线数量 -->
<script setup lang="ts">
import ScreenPanel from './ScreenPanel.vue'
import type { ScreenSummary } from '@/api/screen'

defineProps<{ data: ScreenSummary | null }>()

const items = [
  { key: 'vehicle_count', label: '车辆总数', color: '#38bdf8', icon: '🚛' },
  { key: 'online_count',  label: '在线车辆', color: '#34d399', icon: '📡' },
  { key: 'fleet_count',   label: '车队数量', color: '#a78bfa', icon: '🏢' },
  { key: 'user_count',    label: '用户数量', color: '#fbbf24', icon: '👤' },
] as const
</script>

<template>
  <ScreenPanel title="运营概览">
    <div class="summary-grid">
      <div
        v-for="item in items"
        :key="item.key"
        class="summary-card"
        :style="{ '--acc': item.color }"
      >
        <span class="s-icon">{{ item.icon }}</span>
        <div class="s-val">{{ data ? data[item.key] : '—' }}</div>
        <div class="s-label">{{ item.label }}</div>
      </div>
    </div>
  </ScreenPanel>
</template>

<style scoped>
.summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  height: 100%;
}
.summary-card {
  background: rgba(0, 30, 80, 0.6);
  border: 1px solid color-mix(in srgb, var(--acc) 30%, transparent);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 4px;
  gap: 2px;
  transition: border-color .2s;
}
.summary-card:hover { border-color: var(--acc); }
.s-icon { font-size: 18px; line-height: 1; }
.s-val {
  font-size: 26px;
  font-weight: 700;
  color: var(--acc);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.s-label { font-size: 11px; color: rgba(180, 210, 240, 0.7); }
</style>
