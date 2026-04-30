<script setup lang="ts">
defineOptions({ name: 'VehiclesView' })
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { vehiclesApi } from '@/api/vehicles'
import { devicesApi } from '@/api/devices'
import { fleetsApi } from '@/api/fleets'
import { useAuthStore } from '@/stores/auth'
import VehicleStatusTag from '@/components/VehicleStatusTag.vue'
import type { Vehicle, VehicleCreate, Device, Fleet } from '@/types'

const authStore = useAuthStore()
const route = useRoute()

const vehicles = ref<Vehicle[]>([])
const devices = ref<Device[]>([])
const fleets = ref<Fleet[]>([])
const loading = ref(false)

// Dialog state
const dialogVisible = ref(false)
const dialogTitle = ref('')
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = ref<VehicleCreate & { id?: number }>({
  license_plate: '',
  vehicle_type: 'truck',
  fleet_id: undefined,
  load_capacity: undefined,
  driver_name: '',
  notes: '',
})

// Bind device dialog
const bindDialogVisible = ref(false)
const bindVehicleId = ref<number | null>(null)
const selectedDeviceId = ref<number | null>(null)
// original device bound to the vehicle before the dialog opens (needed for unbind)
const originalDeviceId = ref<number | null>(null)

const vehicleTypeOptions = [
  { label: '货车', value: 'truck' },
  { label: '装载机', value: 'loader' },
  { label: '家用车', value: 'passenger_car' },
  { label: '其他', value: 'other' },
]

const showLoadCapacityField = computed(() => form.value.vehicle_type !== 'passenger_car')

watch(
  () => form.value.vehicle_type,
  (t) => {
    if (t === 'passenger_car') form.value.load_capacity = undefined
  },
)

async function loadData() {
  loading.value = true
  try {
    const [v, d, f] = await Promise.all([
      vehiclesApi.list(),
      devicesApi.list(),
      authStore.isManager ? fleetsApi.list() : Promise.resolve([]),
    ])
    vehicles.value = v
    devices.value = d
    fleets.value = f
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadData()
  await scrollToHighlight()
})

function openCreate() {
  editingId.value = null
  dialogTitle.value = '新增车辆'
  form.value = {
    license_plate: '',
    vehicle_type: 'truck',
    fleet_id: undefined,
    load_capacity: undefined,
    driver_name: '',
    notes: '',
  }
  dialogVisible.value = true
}

function openEdit(row: Vehicle) {
  editingId.value = row.id
  dialogTitle.value = '编辑车辆'
  form.value = {
    license_plate: row.license_plate,
    vehicle_type: row.vehicle_type,
    fleet_id: row.fleet_id ?? undefined,
    load_capacity: row.load_capacity ?? undefined,
    driver_name: row.driver_name ?? '',
    notes: row.notes ?? '',
  }
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value!.validate()
  if (editingId.value) {
    await vehiclesApi.update(editingId.value, form.value)
    ElMessage.success('更新成功')
  } else {
    await vehiclesApi.create(form.value)
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false
  await loadData()
}

async function handleDelete(row: Vehicle) {
  await ElMessageBox.confirm(`确认删除车辆「${row.license_plate}」？`, '警告', {
    type: 'warning',
    confirmButtonText: '删除',
    confirmButtonClass: 'el-button--danger',
  })
  await vehiclesApi.delete(row.id)
  ElMessage.success('已删除')
  await loadData()
}

function openBind(vehicle: Vehicle) {
  bindVehicleId.value = vehicle.id
  selectedDeviceId.value = vehicle.device_id
  originalDeviceId.value = vehicle.device_id   // remember for unbind
  bindDialogVisible.value = true
}

async function handleBind() {
  if (!bindVehicleId.value) return
  if (selectedDeviceId.value) {
    // POST /api/devices/{device_id}/bind  { vehicle_id }
    await devicesApi.bind(selectedDeviceId.value, bindVehicleId.value)
    ElMessage.success('绑定成功')
  } else if (originalDeviceId.value) {
    // POST /api/devices/{device_id}/unbind
    await devicesApi.unbind(originalDeviceId.value)
    ElMessage.success('已解绑')
  }
  bindDialogVisible.value = false
  await loadData()
}

const unboundDevices = computed(() =>
  devices.value.filter((d) => !d.vehicle_id || d.vehicle_id === bindVehicleId.value),
)

const highlightId = computed(() => {
  const h = route.query.highlight
  if (h == null || h === '') return null
  const n = Number(Array.isArray(h) ? h[0] : h)
  return Number.isFinite(n) ? n : null
})

function rowClassName({ row }: { row: Vehicle }) {
  if (highlightId.value != null && row.id === highlightId.value) return 'row-highlight'
  return ''
}

const tableRef = ref<InstanceType<typeof import('element-plus')['ElTable']> | null>(null)

async function scrollToHighlight() {
  await nextTick()
  const id = highlightId.value
  if (id == null) return
  const wrap = tableRef.value?.$el as HTMLElement | undefined
  const rowEl = wrap?.querySelector('.row-highlight') as HTMLElement | undefined
  rowEl?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

watch(highlightId, () => { void scrollToHighlight() })
watch(vehicles, () => { void scrollToHighlight() })
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>车辆管理</h3>
      <el-button type="primary" :icon="'Plus'" @click="openCreate">新增车辆</el-button>
    </div>

    <el-table
      ref="tableRef"
      :data="vehicles"
      v-loading="loading"
      border
      stripe
      :row-class-name="rowClassName"
    >
      <el-table-column label="ID" prop="id" width="60" />
      <el-table-column label="车牌号" prop="license_plate" width="120" />
      <el-table-column label="车型" width="90">
        <template #default="{ row }">
          {{ vehicleTypeOptions.find((o) => o.value === row.vehicle_type)?.label ?? row.vehicle_type }}
        </template>
      </el-table-column>
      <el-table-column label="载重(t)" prop="load_capacity" width="80" align="center">
        <template #default="{ row }">{{ row.load_capacity ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="驾驶员" width="100">
        <template #default="{ row }">
          <span v-if="row.driver_name">{{ row.driver_name }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="所属车队" min-width="100">
        <template #default="{ row }">
          <span v-if="row.fleet_name">{{ row.fleet_name }}</span>
          <el-tag v-else type="info" size="small">未分配</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="绑定设备" min-width="155">
        <template #default="{ row }">
          <span v-if="row.device_imei" class="imei-text">{{ row.device_imei }}</span>
          <el-tag v-else type="info" size="small">未绑定</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="185" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="primary" @click="openBind(row)">绑定设备</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create / Edit dialog -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px" draggable>
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item
          label="车牌号"
          prop="license_plate"
          :rules="[{ required: true, message: '请输入车牌号' }]"
        >
          <el-input v-model="form.license_plate" placeholder="如 鄂Q12345" />
        </el-form-item>
        <el-form-item label="车型" prop="vehicle_type">
          <el-select v-model="form.vehicle_type" style="width: 100%">
            <el-option v-for="o in vehicleTypeOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="showLoadCapacityField" label="载重(t)" prop="load_capacity">
          <el-input-number v-model="form.load_capacity" :min="0" :precision="1" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item label="驾驶员">
          <el-input v-model="form.driver_name" placeholder="请输入驾驶员姓名（可选）" clearable />
        </el-form-item>
        <el-form-item v-if="authStore.isManager" label="所属车队">
          <el-select v-model="form.fleet_id" placeholder="选择车队（可选）" clearable style="width: 100%">
            <el-option v-for="f in fleets" :key="f.id" :label="f.name" :value="f.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>

    <!-- Bind device dialog -->
    <el-dialog v-model="bindDialogVisible" title="绑定设备" width="420px">
      <el-form label-width="80px">
        <el-form-item label="选择设备">
          <el-select
            v-model="selectedDeviceId"
            placeholder="选择设备（置空则解绑）"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="d in unboundDevices"
              :key="d.id"
              :label="`IMEI: ${d.imei}`"
              :value="d.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="bindDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleBind">确认</el-button>
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

.muted {
  color: #c0c4cc;
  font-size: 12px;
}

.imei-text {
  font-family: monospace;
  font-size: 12px;
  color: #555;
}

:deep(.el-table .row-highlight > td) {
  background-color: #e6f4ff !important;
}
</style>
