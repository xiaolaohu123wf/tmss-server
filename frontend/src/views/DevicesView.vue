<script setup lang="ts">
defineOptions({ name: 'DevicesView' })
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { devicesApi } from '@/api/devices'
import DeviceStatusTag from '@/components/DeviceStatusTag.vue'
import type { Device } from '@/types'
import { chinaTimeZoneLabel, formatChinaDateTimeSplit } from '@/utils/datetime'

const authStore = useAuthStore()
const devices = ref<Device[]>([])
const loading = ref(false)

// Create dialog
const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = ref({ imei: '', firmware_version: '' })

// Send command dialog
const commandVisible = ref(false)
const commandDeviceId = ref<number | null>(null)
const commandDeviceImei = ref('')
const selectedCommand = ref('')
const commandLoading = ref(false)

// Edit metadata dialog
const editVisible = ref(false)
const editDeviceId = ref<number | null>(null)
const editForm = ref({ firmware_version: '', iccid: '' })
const editLoading = ref(false)

const COMMANDS = [
  { label: 'gm — 早上欢迎语', value: 'gm' },
  { label: 'ga — 下午欢迎语', value: 'ga' },
  { label: 'gn — 晚上欢迎语', value: 'gn' },
  { label: 'ws — 超速提醒', value: 'ws' },
  { label: 'wa — 越界提醒', value: 'wa' },
  { label: 'vs — 车辆调度', value: 'vs' },
]

async function loadData() {
  loading.value = true
  try {
    devices.value = await devicesApi.list()
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

async function handleCreate() {
  await createFormRef.value!.validate()
  await devicesApi.create({ imei: createForm.value.imei, firmware_version: createForm.value.firmware_version || undefined })
  ElMessage.success('设备已添加')
  createVisible.value = false
  await loadData()
}

function openCommand(device: Device) {
  commandDeviceId.value = device.id
  commandDeviceImei.value = device.imei
  selectedCommand.value = ''
  commandVisible.value = true
}

function openEdit(device: Device) {
  editDeviceId.value = device.id
  editForm.value = {
    firmware_version: device.firmware_version ?? '',
    iccid: device.iccid ?? '',
  }
  editVisible.value = true
}

async function handleEditSave() {
  if (!editDeviceId.value) return
  editLoading.value = true
  try {
    await devicesApi.update(editDeviceId.value, {
      firmware_version: editForm.value.firmware_version,
      iccid: editForm.value.iccid,
    })
    ElMessage.success('设备信息已保存')
    editVisible.value = false
    await loadData()
  } finally {
    editLoading.value = false
  }
}

async function handleSendCommand() {
  if (!commandDeviceId.value || !selectedCommand.value) return
  commandLoading.value = true
  try {
    const res = await devicesApi.sendCommand(commandDeviceId.value, selectedCommand.value)
    const speedHint =
      res.speed_kmh_recorded != null
        ? `（记录速度 ${Number(res.speed_kmh_recorded).toFixed(1)} km/h）`
        : ''
    if (res?.delivered === false) {
      ElMessage.warning((res.message ?? '设备不在线') + speedHint)
    } else {
      ElMessage.success(`指令 ${selectedCommand.value} 下发成功${speedHint}`)
    }
    commandVisible.value = false
  } finally {
    commandLoading.value = false
  }
}

async function handleUnbind(device: Device) {
  if (!device.vehicle_id) return
  await ElMessageBox.confirm(`确认解绑设备 ${device.imei} 与车辆？`, '确认', { type: 'warning' })
  await devicesApi.unbind(device.id)
  ElMessage.success('已解绑')
  await loadData()
}

async function handleDelete(device: Device) {
  await ElMessageBox.confirm(
    `确认删除设备「${device.imei}」？删除后设备记录不再显示，历史定位等数据仍保留；同一 IMEI 再次连接将自动新建设备。`,
    '删除设备',
    {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      confirmButtonClass: 'el-button--danger',
    },
  )
  await devicesApi.delete(device.id)
  ElMessage.success('设备已删除')
  await loadData()
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>设备管理</h3>
      <el-button type="primary" :icon="'Plus'" @click="createVisible = true">添加设备</el-button>
    </div>

    <el-table :data="devices" v-loading="loading" border stripe>
      <el-table-column label="ID" prop="id" width="60" />
      <el-table-column label="IMEI" prop="imei" min-width="155">
        <template #default="{ row }">
          <span class="mono">{{ row.imei }}</span>
        </template>
      </el-table-column>
      <el-table-column label="定位状态" width="120">
        <template #default="{ row }">
          <DeviceStatusTag :device="row" />
        </template>
      </el-table-column>
      <el-table-column label="最后定位" width="95">
        <template #default="{ row }">
          <template v-if="row.last_location_at">
            <div class="time-text">{{ formatChinaDateTimeSplit(row.last_location_at).date }}</div>
            <div class="time-text secondary">
              {{ formatChinaDateTimeSplit(row.last_location_at).time }} · {{ chinaTimeZoneLabel() }}
            </div>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="坐标" width="175">
        <template #default="{ row }">
          <template v-if="row.last_lat != null">
            <span class="mono coord">
              {{ row.last_lat.toFixed(5) }}, {{ row.last_lng.toFixed(5) }}
            </span>
            <el-tag
              :type="row.last_loc_type === 'gps' ? 'success' : 'primary'"
              size="small"
              style="margin-left:4px;vertical-align:middle"
            >
              {{ row.last_loc_type?.toUpperCase() ?? '' }}
            </el-tag>
          </template>
          <span v-else class="muted">未定位</span>
        </template>
      </el-table-column>
      <el-table-column label="心跳时间" width="95">
        <template #default="{ row }">
          <template v-if="row.last_heartbeat_at">
            <div class="time-text">{{ formatChinaDateTimeSplit(row.last_heartbeat_at).date }}</div>
            <div class="time-text secondary">
              {{ formatChinaDateTimeSplit(row.last_heartbeat_at).time }} · {{ chinaTimeZoneLabel() }}
            </div>
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="固件" prop="firmware_version" width="90">
        <template #default="{ row }">
          <span class="muted">{{ row.firmware_version ?? '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="ICCID" prop="iccid" min-width="150">
        <template #default="{ row }">
          <span class="mono small">{{ row.iccid ?? '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="绑定车辆" width="110">
        <template #default="{ row }">
          <span v-if="row.vehicle_license" class="plate">{{ row.vehicle_license }}</span>
          <el-tag v-else type="info" size="small">未绑定</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="232" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="primary" :disabled="!row.online" @click="openCommand(row)">
            下发指令
          </el-button>
          <el-button v-if="row.vehicle_id" link type="warning" @click="handleUnbind(row)">
            解绑
          </el-button>
          <el-button v-if="authStore.isManager" link type="danger" @click="handleDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Add device dialog -->
    <el-dialog v-model="createVisible" title="添加设备" width="420px">
      <el-form ref="createFormRef" :model="createForm" label-width="100px">
        <el-form-item
          label="IMEI"
          prop="imei"
          :rules="[{ required: true, message: '请输入 IMEI' }, { len: 15, message: 'IMEI 为 15 位' }]"
        >
          <el-input v-model="createForm.imei" placeholder="15 位 IMEI 码" maxlength="15" />
        </el-form-item>
        <el-form-item label="固件版本">
          <el-input v-model="createForm.firmware_version" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">添加</el-button>
      </template>
    </el-dialog>

    <!-- Edit device metadata -->
    <el-dialog v-model="editVisible" title="编辑设备" width="440px">
      <el-form label-width="100px">
        <el-form-item label="固件版本">
          <el-input v-model="editForm.firmware_version" placeholder="如 1.0.0" clearable />
        </el-form-item>
        <el-form-item label="ICCID">
          <el-input v-model="editForm.iccid" placeholder="SIM 卡 ICCID" clearable maxlength="22" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editLoading" @click="handleEditSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- Send command dialog -->
    <el-dialog v-model="commandVisible" title="手动下发指令" width="420px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="目标设备 IMEI">
          <span class="mono">{{ commandDeviceImei }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-form label-width="80px" style="margin-top: 16px">
        <el-form-item label="指令">
          <el-select v-model="selectedCommand" placeholder="选择指令" style="width: 100%">
            <el-option
              v-for="cmd in COMMANDS"
              :key="cmd.value"
              :label="cmd.label"
              :value="cmd.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="commandVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="commandLoading"
          :disabled="!selectedCommand"
          @click="handleSendCommand"
        >
          下发
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.mono {
  font-family: monospace;
  font-size: 12px;
}

.mono.small {
  font-size: 11px;
}

.coord {
  font-size: 11px;
}

.time-text {
  font-size: 12px;
  line-height: 1.4;
  color: #303133;
}

.time-text.secondary {
  color: #86909c;
}

.muted {
  color: #c0c4cc;
  font-size: 12px;
}

.plate {
  font-weight: 600;
  font-size: 13px;
  color: #1d2129;
}
</style>
