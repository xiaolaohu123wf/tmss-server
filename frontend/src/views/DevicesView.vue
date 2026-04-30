<script setup lang="ts">
defineOptions({ name: 'DevicesView' })
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { devicesApi } from '@/api/devices'
import DeviceOnlineBadge from '@/components/DeviceOnlineBadge.vue'
import type { Device } from '@/types'

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

async function handleSendCommand() {
  if (!commandDeviceId.value || !selectedCommand.value) return
  commandLoading.value = true
  try {
    await devicesApi.sendCommand(commandDeviceId.value, selectedCommand.value)
    ElMessage.success(`指令 ${selectedCommand.value} 下发成功`)
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
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>设备管理</h3>
      <el-button type="primary" :icon="'Plus'" @click="createVisible = true">添加设备</el-button>
    </div>

    <el-table :data="devices" v-loading="loading" border stripe>
      <el-table-column label="ID" prop="id" width="70" />
      <el-table-column label="IMEI" prop="imei" min-width="160">
        <template #default="{ row }">
          <span class="mono">{{ row.imei }}</span>
        </template>
      </el-table-column>
      <el-table-column label="在线状态" width="100">
        <template #default="{ row }">
          <DeviceOnlineBadge :online="row.online" />
        </template>
      </el-table-column>
      <el-table-column label="最后心跳" prop="last_heartbeat_at" width="170" />
      <el-table-column label="固件版本" prop="firmware_version" width="120" />
      <el-table-column label="ICCID" prop="iccid" min-width="160">
        <template #default="{ row }">
          <span class="mono">{{ row.iccid ?? '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="绑定车辆" width="140">
        <template #default="{ row }">
          <span v-if="row.vehicle_license">{{ row.vehicle_license }}</span>
          <el-tag v-else type="info" size="small">未绑定</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" :disabled="!row.online" @click="openCommand(row)">
            下发指令
          </el-button>
          <el-button
            v-if="row.vehicle_id"
            link
            type="warning"
            @click="handleUnbind(row)"
          >
            解绑
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
</style>
