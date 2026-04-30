<script setup lang="ts">
defineOptions({ name: 'EventsView' })
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { eventsApi } from '@/api/events'
import EventTypeTag from '@/components/EventTypeTag.vue'
import type { TmssEvent, EventType, EventQuery } from '@/types'
import dayjs from 'dayjs'
import { chinaTimeZoneLabel, formatChinaDateTimeSplit } from '@/utils/datetime'

const router = useRouter()

const events = ref<TmssEvent[]>([])
const total = ref(0)
const loading = ref(false)

const query = reactive<EventQuery>({
  page: 1,
  size: 20,
  event_type: undefined,
  start: undefined,
  end: undefined,
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
  { label: '手动指令',   value: 'manual_command' },
]

async function loadData() {
  loading.value = true
  try {
    if (dateRange.value) {
      query.start = dayjs(dateRange.value[0]).toISOString()
      query.end   = dayjs(dateRange.value[1]).toISOString()
    } else {
      query.start = undefined
      query.end   = undefined
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
  query.start = undefined
  query.end = undefined
  dateRange.value = null
  query.page = 1
  loadData()
}

function handlePageChange(page: number) {
  query.page = page
  loadData()
}

function goVehicle(row: TmssEvent) {
  if (row.vehicle_id == null) return
  router.push({ name: 'vehicles', query: { highlight: String(row.vehicle_id) } })
}

function isManualEvent(row: TmssEvent): boolean {
  if (row.event_type === 'manual_command') return true
  const d = row.detail
  if (d == null || typeof d !== 'object') return false
  return (d as Record<string, unknown>).source === 'manual'
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
      <el-table-column label="ID" prop="id" width="70" />
      <el-table-column label="事件类型" width="120">
        <template #default="{ row }">
          <EventTypeTag :type="row.event_type" />
        </template>
      </el-table-column>
      <el-table-column label="车辆" width="130">
        <template #default="{ row }">
          <el-button
            v-if="row.vehicle_id"
            link
            type="primary"
            class="plate-btn"
            @click="goVehicle(row)"
          >
            {{ row.vehicle_license ?? `车辆 #${row.vehicle_id}` }}
          </el-button>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="速度(km/h)" prop="speed" width="100" align="center">
        <template #default="{ row }">{{ row.speed != null ? row.speed.toFixed(1) : '—' }}</template>
      </el-table-column>
      <el-table-column label="坐标" min-width="175">
        <template #default="{ row }">
          <span v-if="row.lat != null" class="mono">{{ row.lat.toFixed(5) }}, {{ row.lng.toFixed(5) }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="发生时间" width="185">
        <template #default="{ row }">
          <template v-if="row.occurred_at">
            <div>{{ formatChinaDateTimeSplit(row.occurred_at).date }}</div>
            <div class="time-secondary">
              {{ formatChinaDateTimeSplit(row.occurred_at).time }} · {{ chinaTimeZoneLabel() }}
            </div>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="附加信息" min-width="200">
        <template #default="{ row }">
          <div class="extra-wrap">
            <el-tag
              v-if="isManualEvent(row)"
              type="warning"
              size="small"
              effect="plain"
              class="tag-manual"
            >
              手动下发
            </el-tag>
            <span v-if="row.cmd_sent" class="cmd-tag">{{ row.cmd_sent }}</span>
            <span v-if="row.detail" class="mono small detail-json">{{ JSON.stringify(row.detail) }}</span>
            <span v-if="!row.detail && !row.cmd_sent && !isManualEvent(row)" class="muted">—</span>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="query.page"
      v-model:page-size="query.size"
      :total="total"
      layout="total, prev, pager, next, sizes"
      :page-sizes="[10, 20, 50, 100]"
      style="margin-top: 16px; justify-content: flex-end"
      @current-change="handlePageChange"
      @size-change="(s: number) => { query.size = s; query.page = 1; loadData() }"
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

.plate-btn {
  font-weight: 600;
  padding: 0;
}

.muted {
  color: #c0c4cc;
  font-size: 12px;
}

.time-secondary {
  font-size: 11px;
  color: #86909c;
  line-height: 1.3;
}

.mono.small {
  font-size: 11px;
}

.cmd-tag {
  display: inline-block;
  background: #f0f2f5;
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 11px;
  font-family: monospace;
  color: #595959;
  margin-right: 6px;
}

.extra-wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.tag-manual {
  flex-shrink: 0;
}

.detail-json {
  word-break: break-all;
}
</style>
