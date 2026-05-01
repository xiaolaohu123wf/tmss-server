<script setup lang="ts">
defineOptions({ name: 'DevicesView' })
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { devicesApi } from '@/api/devices'
import { vehiclesApi } from '@/api/vehicles'
import DeviceStatusTag from '@/components/DeviceStatusTag.vue'
import type { Device, Vehicle } from '@/types'
import { formatChinaDateTimeSplit } from '@/utils/datetime'

const authStore = useAuthStore()

// ── 数据 ──────────────────────────────────────────────────────────────────────
const allDevices = ref<Device[]>([])
const unboundDevices = ref<Device[]>([])
const loading = ref(false)
const unboundLoading = ref(false)

// 车队长：只看本队设备
const myDevices = computed(() =>
  authStore.isManager
    ? allDevices.value
    : allDevices.value.filter(d => d.fleet_id === authStore.session?.fleet_id)
)

// ── 弹窗状态 ───────────────────────────────────────────────────────────────────
const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = ref({ imei: '' })

const editVisible = ref(false)
const editDeviceId = ref<number | null>(null)
const editCurrentFirmware = ref('')
const editForm = ref({ iccid: '' })
const editLoading = ref(false)

const commandVisible = ref(false)
const commandDeviceId = ref<number | null>(null)
const commandDeviceImei = ref('')
const selectedCommand = ref('')
const commandLoading = ref(false)

// 车队长绑定弹窗
const bindVisible = ref(false)
const bindTargetDevice = ref<Device | null>(null)
const bindVehicleId = ref<number | null>(null)
const myVehicles = ref<Vehicle[]>([])
const bindLoading = ref(false)

const activeTab = ref('my')

const COMMANDS = [
  { label: 'gm — 早上欢迎语', value: 'gm' },
  { label: 'ga — 下午欢迎语', value: 'ga' },
  { label: 'gn — 晚上欢迎语', value: 'gn' },
  { label: 'ws — 超速提醒',   value: 'ws' },
  { label: 'wa — 越界提醒',   value: 'wa' },
  { label: 'vs — 车辆调度',   value: 'vs' },
]

// ── 加载 ───────────────────────────────────────────────────────────────────────
async function loadAll() {
  loading.value = true
  try { allDevices.value = await devicesApi.list() }
  finally { loading.value = false }
}

async function loadUnbound() {
  unboundLoading.value = true
  try { unboundDevices.value = await devicesApi.list({ unbound: true }) }
  finally { unboundLoading.value = false }
}

async function loadData() {
  await loadAll()
  if (!authStore.isManager) await loadUnbound()
}

onMounted(loadData)

// ── 管理员：创建设备 ───────────────────────────────────────────────────────────
async function handleCreate() {
  try { await createFormRef.value!.validate() } catch { return }
  await devicesApi.create({ imei: createForm.value.imei })
  ElMessage.success('设备已添加')
  createVisible.value = false
  await loadData()
}

// ── 编辑 ───────────────────────────────────────────────────────────────────────
function openEdit(device: Device) {
  editDeviceId.value = device.id
  editCurrentFirmware.value = device.firmware_version ?? '—'
  editForm.value = { iccid: device.iccid ?? '' }
  editVisible.value = true
}

async function handleEditSave() {
  if (!editDeviceId.value) return
  editLoading.value = true
  try {
    await devicesApi.update(editDeviceId.value, { iccid: editForm.value.iccid })
    ElMessage.success('已保存')
    editVisible.value = false
    await loadData()
  } finally { editLoading.value = false }
}

// ── 指令 ───────────────────────────────────────────────────────────────────────
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
    const res = await devicesApi.sendCommand(commandDeviceId.value, selectedCommand.value)
    const hint = res.speed_kmh_recorded != null ? `（记录速度 ${Number(res.speed_kmh_recorded).toFixed(1)} km/h）` : ''
    res?.delivered === false ? ElMessage.warning((res.message ?? '设备不在线') + hint) : ElMessage.success(`指令下发成功${hint}`)
    commandVisible.value = false
  } finally { commandLoading.value = false }
}

// ── 解绑 ───────────────────────────────────────────────────────────────────────
async function handleUnbind(device: Device) {
  if (!device.vehicle_id) return
  await ElMessageBox.confirm(`确认解绑设备 ${device.imei} 与车辆「${device.vehicle_license}」？`, '确认', { type: 'warning', lockScroll: false })
  await devicesApi.unbind(device.id)
  ElMessage.success('已解绑')
  await loadData()
}

// ── 删除（仅管理员） ───────────────────────────────────────────────────────────
async function handleDelete(device: Device) {
  await ElMessageBox.confirm(`确认删除设备「${device.imei}」？`, '删除设备', {
    type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger', lockScroll: false,
  })
  await devicesApi.delete(device.id)
  ElMessage.success('设备已删除')
  await loadData()
}

// ── 车队长：绑定未绑定设备 ────────────────────────────────────────────────────
async function openBind(device: Device) {
  bindTargetDevice.value = device
  bindVehicleId.value = null
  bindVisible.value = true
  bindLoading.value = true
  try { myVehicles.value = await vehiclesApi.list() }
  finally { bindLoading.value = false }
}

// 只允许绑定到尚未绑定设备的本队车辆
const bindableVehicles = computed(() => myVehicles.value.filter(v => !v.device_id))

async function handleBind() {
  if (!bindTargetDevice.value || !bindVehicleId.value) return
  await devicesApi.bind(bindTargetDevice.value.id, bindVehicleId.value)
  ElMessage.success('绑定成功')
  bindVisible.value = false
  await loadData()
}

async function onTabChange(pane: { paneName: string }) {
  activeTab.value = pane.paneName
  if (pane.paneName === 'unbound') await loadUnbound()
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>设备管理</h3>
      <el-button v-if="authStore.isManager" type="primary" :icon="'Plus'" @click="createVisible = true">
        添加设备
      </el-button>
    </div>

    <!-- ════ 管理员：完整设备表 ════ -->
    <template v-if="authStore.isManager">
      <el-table :data="allDevices" v-loading="loading" border stripe>
        <el-table-column label="ID" prop="id" width="60" />
        <el-table-column label="IMEI" prop="imei" min-width="155">
          <template #default="{ row }"><span class="mono">{{ row.imei }}</span></template>
        </el-table-column>
        <el-table-column label="定位状态" width="120">
          <template #default="{ row }"><DeviceStatusTag :device="row" /></template>
        </el-table-column>
        <el-table-column label="最后定位" width="95">
          <template #default="{ row }">
            <template v-if="row.last_location_at">
              <div class="time-text">{{ formatChinaDateTimeSplit(row.last_location_at).date }}</div>
              <div class="time-text secondary">{{ formatChinaDateTimeSplit(row.last_location_at).time }}</div>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="心跳时间" width="95">
          <template #default="{ row }">
            <template v-if="row.last_heartbeat_at">
              <div class="time-text">{{ formatChinaDateTimeSplit(row.last_heartbeat_at).date }}</div>
              <div class="time-text secondary">{{ formatChinaDateTimeSplit(row.last_heartbeat_at).time }}</div>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="固件" prop="firmware_version" width="90">
          <template #default="{ row }"><span class="muted">{{ row.firmware_version ?? '—' }}</span></template>
        </el-table-column>
        <el-table-column label="ICCID" prop="iccid" min-width="150">
          <template #default="{ row }"><span class="mono small">{{ row.iccid ?? '—' }}</span></template>
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
            <el-button link type="primary" :disabled="!row.online" @click="openCommand(row)">下发指令</el-button>
            <el-button v-if="row.vehicle_id" link type="warning" @click="handleUnbind(row)">解绑</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ════ 车队长：双 Tab 视图 ════ -->
    <template v-else>
      <el-tabs :model-value="activeTab" @tab-click="onTabChange">

        <!-- Tab 1：我的设备（本队已绑定的） -->
        <el-tab-pane label="我的设备" name="my">
          <el-table :data="myDevices" v-loading="loading" border stripe>
            <el-table-column label="IMEI" prop="imei" min-width="155">
              <template #default="{ row }"><span class="mono">{{ row.imei }}</span></template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }"><DeviceStatusTag :device="row" /></template>
            </el-table-column>
            <el-table-column label="绑定车辆" width="120">
              <template #default="{ row }">
                <span v-if="row.vehicle_license" class="plate">{{ row.vehicle_license }}</span>
                <el-tag v-else type="info" size="small">未绑定</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="最后定位" width="95">
              <template #default="{ row }">
                <template v-if="row.last_location_at">
                  <div class="time-text">{{ formatChinaDateTimeSplit(row.last_location_at).date }}</div>
                  <div class="time-text secondary">{{ formatChinaDateTimeSplit(row.last_location_at).time }}</div>
                </template>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="心跳" width="95">
              <template #default="{ row }">
                <template v-if="row.last_heartbeat_at">
                  <div class="time-text">{{ formatChinaDateTimeSplit(row.last_heartbeat_at).date }}</div>
                  <div class="time-text secondary">{{ formatChinaDateTimeSplit(row.last_heartbeat_at).time }}</div>
                </template>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" :disabled="!row.online" @click="openCommand(row)">下发指令</el-button>
                <el-button v-if="row.vehicle_id" link type="warning" @click="handleUnbind(row)">解绑</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!loading && myDevices.length === 0" class="empty-hint">
            本车队暂无绑定设备，请前往「可绑定设备」Tab 绑定
          </div>
        </el-tab-pane>

        <!-- Tab 2：可绑定设备（全局未绑定） -->
        <el-tab-pane label="可绑定设备" name="unbound">
          <el-table :data="unboundDevices" v-loading="unboundLoading" border stripe>
            <el-table-column label="IMEI" prop="imei" min-width="155">
              <template #default="{ row }"><span class="mono">{{ row.imei }}</span></template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }"><DeviceStatusTag :device="row" /></template>
            </el-table-column>
            <el-table-column label="最后定位" width="95">
              <template #default="{ row }">
                <template v-if="row.last_location_at">
                  <div class="time-text">{{ formatChinaDateTimeSplit(row.last_location_at).date }}</div>
                  <div class="time-text secondary">{{ formatChinaDateTimeSplit(row.last_location_at).time }}</div>
                </template>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="ICCID" prop="iccid" min-width="150">
              <template #default="{ row }"><span class="mono small">{{ row.iccid ?? '—' }}</span></template>
            </el-table-column>
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openBind(row)">绑定到车辆</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!unboundLoading && unboundDevices.length === 0" class="empty-hint">
            暂无可绑定的空闲设备
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>

    <!-- ── 添加设备弹窗（管理员） ── -->
    <el-dialog v-model="createVisible" title="添加设备" width="420px">
      <el-form ref="createFormRef" :model="createForm" label-width="100px">
        <el-form-item label="IMEI" prop="imei"
          :rules="[{ required: true, message: '请输入 IMEI' }, { len: 15, message: 'IMEI 为 15 位' }]">
          <el-input v-model="createForm.imei" placeholder="15 位 IMEI 码" maxlength="15" />
        </el-form-item>
        <el-form-item label="固件版本">
          <el-text type="info" size="small">设备开机后自动上报</el-text>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">添加</el-button>
      </template>
    </el-dialog>

    <!-- ── 编辑设备弹窗 ── -->
    <el-dialog v-model="editVisible" title="编辑设备" width="440px">
      <el-form label-width="100px">
        <el-form-item label="固件版本">
          <span style="font-size:13px;color:#606266">{{ editCurrentFirmware }}</span>
          <el-text type="info" size="small" style="margin-left:8px">由设备开机自动上报</el-text>
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

    <!-- ── 下发指令弹窗 ── -->
    <el-dialog v-model="commandVisible" title="手动下发指令" width="420px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="目标设备 IMEI">
          <span class="mono">{{ commandDeviceImei }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-form label-width="80px" style="margin-top: 16px">
        <el-form-item label="指令">
          <el-select v-model="selectedCommand" placeholder="选择指令" style="width: 100%">
            <el-option v-for="cmd in COMMANDS" :key="cmd.value" :label="cmd.label" :value="cmd.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="commandVisible = false">取消</el-button>
        <el-button type="primary" :loading="commandLoading" :disabled="!selectedCommand" @click="handleSendCommand">下发</el-button>
      </template>
    </el-dialog>

    <!-- ── 车队长：绑定设备到车辆弹窗 ── -->
    <el-dialog v-model="bindVisible" title="绑定设备到车辆" width="440px">
      <el-descriptions :column="1" border size="small" style="margin-bottom:16px">
        <el-descriptions-item label="设备 IMEI">
          <span class="mono">{{ bindTargetDevice?.imei }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-form label-width="90px" v-loading="bindLoading">
        <el-form-item label="选择车辆">
          <el-select v-model="bindVehicleId" placeholder="选择本队车辆" style="width:100%" filterable>
            <el-option
              v-for="v in bindableVehicles"
              :key="v.id"
              :label="`${v.license_plate}${v.driver_name ? ' · ' + v.driver_name : ''}`"
              :value="v.id"
            />
          </el-select>
          <div v-if="!bindLoading && bindableVehicles.length === 0" class="bind-hint">
            所有车辆已绑定设备，请先在车辆管理中解绑后再操作
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="bindVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!bindVehicleId" @click="handleBind">确认绑定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { background: #fff; border-radius: 8px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h3 { margin: 0; font-size: 16px; font-weight: 600; }
.mono { font-family: monospace; font-size: 12px; }
.mono.small { font-size: 11px; }
.time-text { font-size: 12px; line-height: 1.4; color: #303133; }
.time-text.secondary { color: #86909c; }
.muted { color: #c0c4cc; font-size: 12px; }
.plate { font-weight: 600; font-size: 13px; color: #1d2129; }
.empty-hint { padding: 32px; text-align: center; color: #86909c; font-size: 14px; }
.bind-hint { font-size: 12px; color: #e6a23c; margin-top: 6px; }
</style>
