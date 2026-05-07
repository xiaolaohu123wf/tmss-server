<!-- 左侧面板2：车队/车辆列表（可切换） -->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import ScreenPanel from './ScreenPanel.vue'
import { get } from '@/api/index'
import type { Vehicle, Fleet } from '@/types'

const tab = ref<'fleet' | 'vehicle'>('vehicle')
const vehicles = ref<Vehicle[]>([])
const fleets = ref<Fleet[]>([])
const loading = ref(false)

const emit = defineEmits<{ (e: 'select-vehicle', v: Vehicle): void }>()

async function fetchData() {
  loading.value = true
  try {
    const [vList, fList] = await Promise.all([
      get<Vehicle[]>('/vehicles'),
      get<Fleet[]>('/admin/fleets').catch(() => get<{ id: number; name: string }[]>('/fleets/me').then(f => [f])),
    ])
    vehicles.value = vList
    fleets.value = fList as Fleet[]
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)

// 把每辆车的在线状态注入（由父组件通过 onlineIds prop 传入）
const props = defineProps<{ onlineIds?: Set<number> }>()

const vehicleList = computed(() =>
  vehicles.value.map(v => ({ ...v, online: props.onlineIds?.has(v.id) ?? false }))
)
</script>

<template>
  <ScreenPanel title="车队 / 车辆列表">
    <div class="tab-bar">
      <span :class="['tab', tab === 'vehicle' && 'active']" @click="tab = 'vehicle'">车辆</span>
      <span :class="['tab', tab === 'fleet'   && 'active']" @click="tab = 'fleet'">车队</span>
    </div>

    <!-- 车辆列表 -->
    <div v-if="tab === 'vehicle'" class="list-wrap">
      <div
        v-for="v in vehicleList"
        :key="v.id"
        class="list-row"
        @click="emit('select-vehicle', v)"
      >
        <span :class="['dot', v.online ? 'online' : 'offline']" />
        <div class="veh-main">
          <span class="plate">{{ v.license_plate }}</span>
          <span v-if="v.driver_phone" class="veh-phone">{{ v.driver_phone }}</span>
        </div>
        <span class="fleet-name">{{ v.fleet_name ?? '—' }}</span>
        <span :class="['state-badge', v.online ? 'on' : 'off']">
          {{ v.online ? '在线' : '离线' }}
        </span>
      </div>
      <div v-if="!vehicleList.length" class="empty">暂无数据</div>
    </div>

    <!-- 车队列表 -->
    <div v-else class="list-wrap">
      <div v-for="f in fleets" :key="f.id" class="list-row fleet-row">
        <span class="fleet-icon">🏢</span>
        <div class="fleet-info">
          <span class="fleet-nm">{{ f.name }}</span>
          <span class="fleet-sub">
            {{ vehicles.filter(v => v.fleet_id === f.id).length }} 辆车
          </span>
        </div>
      </div>
      <div v-if="!fleets.length" class="empty">暂无数据</div>
    </div>
  </ScreenPanel>
</template>

<style scoped>
.tab-bar {
  display: flex; gap: 4px; margin-bottom: 6px;
}
.tab {
  flex: 1; text-align: center; padding: 4px 0;
  font-size: 11px; color: rgba(150,200,240,.5);
  border: 1px solid rgba(0,180,255,.15); border-radius: 4px;
  cursor: pointer; transition: all .2s;
}
.tab.active {
  color: #00d4ff; border-color: rgba(0,212,255,.5);
  background: rgba(0,212,255,.08);
}

.list-wrap {
  overflow-y: auto; height: calc(100% - 30px);
  scrollbar-width: thin; scrollbar-color: rgba(0,180,255,.3) transparent;
}
.list-row {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 4px; border-radius: 4px;
  cursor: pointer; transition: background .15s;
  border-bottom: 1px solid rgba(0,100,180,.1);
}
.list-row:hover { background: rgba(0,100,200,.15); }

.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.dot.online { background: #34d399; box-shadow: 0 0 6px #34d399; }
.dot.offline { background: #4b5563; }

.plate { font-size: 12px; font-weight: 600; color: #e0f0ff; min-width: 80px; }
.veh-main {
  display: flex; flex-direction: column; gap: 1px; min-width: 72px; flex-shrink: 0;
}
.veh-phone {
  font-size: 10px; color: rgba(125, 211, 252, 0.85); font-variant-numeric: tabular-nums;
}
.fleet-name { font-size: 11px; color: rgba(150,200,240,.6); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.state-badge {
  font-size: 10px; padding: 1px 6px; border-radius: 10px; flex-shrink: 0;
}
.state-badge.on  { background: rgba(52,211,153,.15); color: #34d399; border: 1px solid rgba(52,211,153,.3); }
.state-badge.off { background: rgba(75,85,99,.15);   color: #6b7280; border: 1px solid rgba(75,85,99,.3); }

.fleet-row { cursor: default; }
.fleet-icon { font-size: 16px; }
.fleet-info { display: flex; flex-direction: column; }
.fleet-nm { font-size: 12px; color: #e0f0ff; font-weight: 600; }
.fleet-sub { font-size: 10px; color: rgba(150,200,240,.5); }

.empty { color: rgba(100,160,200,.4); font-size: 12px; text-align: center; padding: 16px; }
</style>
