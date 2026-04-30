<script setup lang="ts">
defineOptions({ name: 'EventsView' })
import { ref, reactive, onMounted } from 'vue'
import { eventsApi } from '@/api/events'
import EventTypeTag from '@/components/EventTypeTag.vue'
import type { TmssEvent, EventType, EventQuery } from '@/types'
import dayjs from 'dayjs'

const events = ref<TmssEvent[]>([])
const total = ref(0)
const loading = ref(false)

const query = reactive<EventQuery>({
  page: 1,
  page_size: 20,
  event_type: undefined,
  start_time: undefined,
  end_time: undefined,
  vehicle_id: undefined,
})

const dateRange = ref<[Date, Date] | null>(null)

const EVENT_TYPES: { label: string; value: EventType }[] = [
  { label: '超速',      value: 'overspeed' },
  { label: '越界',      value: 'geofence_violation' },
  { label: '来车提醒',  value: 'oncoming_warn' },
  { label: '调度',      value: 'dispatch' },
  { label: '禁运违规',  value: 'ban_violation' },
  { label: '进入围栏',  value: 'zone_entry' },
  { label: '离开围栏',  value: 'zone_exit' },
  { label: '设备离线',  value: 'device_offline' },
  { label: '未报备离开',value: 'unreported_exit' },
]

async function loadData() {
  loading.value = true
  try {
    if (dateRange.value) {
      query.start_time = dayjs(dateRange.value[0]).toISOString()
      query.end_time = dayjs(dateRange.value[1]).toISOString()
    } else {
      query.start_time = undefined
      query.end_time = undefined
    }
    const result = await eventsApi.list(query)
    events.value = result.items
    total.value = result.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  query.page = 1
  loadData()
}

function handleReset() {
  query.event_type = undefined
  query.vehicle_id = undefined
  dateRange.value = null
  query.page = 1
  loadData()
}

function handlePageChange(page: number) {
  query.page = page
  loadData()
}

onMounted(loadData)
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>事件查询</h3>
    </div>

    <!-- Filter bar -->
    <el-card shadow="never" class="filter-card">
      <el-form inline>
        <el-form-item label="事件类型">
          <el-select
            v-model="query.event_type"
            placeholder="全部类型"
            clearable
            style="width: 140px"
          >
            <el-option
              v-for="t in EVENT_TYPES"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="时间范围">
          <el-date-picker
            v-model="dateRange"
            type="datetimerange"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 360px"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Results -->
    <el-table :data="events" v-loading="loading" border stripe style="margin-top: 12px">
      <el-table-column label="ID" prop="id" width="80" />
      <el-table-column label="事件类型" width="120">
        <template #default="{ row }">
          <EventTypeTag :type="row.event_type" />
        </template>
      </el-table-column>
      <el-table-column label="车辆" prop="vehicle_license" width="130" />
      <el-table-column label="速度 (km/h)" prop="speed" width="110" />
      <el-table-column label="纬度" prop="lat" width="120" />
      <el-table-column label="经度" prop="lng" width="120" />
      <el-table-column label="发生时间" prop="created_at" min-width="170" />
      <el-table-column label="附加信息" min-width="180">
        <template #default="{ row }">
          <span v-if="row.extra" class="mono">{{ JSON.stringify(row.extra) }}</span>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="query.page"
      v-model:page-size="query.page_size"
      :total="total"
      layout="total, prev, pager, next, sizes"
      :page-sizes="[10, 20, 50, 100]"
      style="margin-top: 16px; justify-content: flex-end"
      @current-change="handlePageChange"
    />
  </div>
</template>

<style scoped>
.page-container {
  background: #f0f2f5;
}

.page-header {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 12px;
}

.page-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.filter-card {
  border-radius: 8px;
}

.mono {
  font-family: monospace;
  font-size: 12px;
}
</style>
