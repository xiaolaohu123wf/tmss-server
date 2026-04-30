<script setup lang="ts">
defineOptions({ name: 'VehiclesView' })
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { vehiclesApi } from '@/api/vehicles'
import { devicesApi } from '@/api/devices'
import VehicleStatusTag from '@/components/VehicleStatusTag.vue'
import type { Vehicle, VehicleCreate, Device } from '@/types'

const vehicles = ref<Vehicle[]>([])
const devices = ref<Device[]>([])
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
})

// Bind device dialog
const bindDialogVisible = ref(false)
const bindVehicleId = ref<number | null>(null)
const selectedDeviceId = ref<number | null>(null)

const vehicleTypeOptions = [
  { label: '货车', value: 'truck' },
  { label: '装载机', value: 'loader' },
  { label: '其他', value: 'other' },
]

async function loadData() {
  loading.value = true
  try {
    [vehicles.value, devices.value] = await Promise.all([
      vehiclesApi.list(),
      devicesApi.list(),
    ])
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

function openCreate() {
  editingId.value = null
  dialogTitle.value = '新增车辆'
  form.value = { license_plate: '', vehicle_type: 'truck' }
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
  bindDialogVisible.value = true
}

async function handleBind() {
  if (!bindVehicleId.value) return
  if (selectedDeviceId.value) {
    await vehiclesApi.bind(bindVehicleId.value, selectedDeviceId.value)
    ElMessage.success('绑定成功')
  } else {
    await vehiclesApi.unbind(bindVehicleId.value)
    ElMessage.success('已解绑')
  }
  bindDialogVisible.value = false
  await loadData()
}

const unboundDevices = computed(() =>
  devices.value.filter((d) => !d.vehicle_id || d.vehicle_id === bindVehicleId.value),
)
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>车辆管理</h3>
      <el-button type="primary" :icon="'Plus'" @click="openCreate">新增车辆</el-button>
    </div>

    <el-table :data="vehicles" v-loading="loading" border stripe>
      <el-table-column label="ID" prop="id" width="70" />
      <el-table-column label="车牌号" prop="license_plate" min-width="120" />
      <el-table-column label="车型" prop="vehicle_type" width="100">
        <template #default="{ row }">
          {{ vehicleTypeOptions.find((o) => o.value === row.vehicle_type)?.label }}
        </template>
      </el-table-column>
      <el-table-column label="载重(t)" prop="load_capacity" width="90" />
      <el-table-column label="车队" prop="fleet_name" min-width="100" />
      <el-table-column label="绑定设备" width="180">
        <template #default="{ row }">
          <span v-if="row.device_imei" class="imei-text">{{ row.device_imei }}</span>
          <el-tag v-else type="info" size="small">未绑定</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="作业状态" width="110">
        <template #default="{ row }">
          <VehicleStatusTag :state="row.work_state" />
        </template>
      </el-table-column>
      <el-table-column label="创建时间" prop="created_at" width="170" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="primary" @click="openBind(row)">绑定设备</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create / Edit dialog -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="500px" draggable>
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item
          label="车牌号"
          prop="license_plate"
          :rules="[{ required: true, message: '请输入车牌号' }]"
        >
          <el-input v-model="form.license_plate" placeholder="如 粤A12345" />
        </el-form-item>
        <el-form-item label="车型" prop="vehicle_type">
          <el-select v-model="form.vehicle_type" style="width: 100%">
            <el-option
              v-for="o in vehicleTypeOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="载重(t)" prop="load_capacity">
          <el-input-number v-model="form.load_capacity" :min="0" :precision="1" style="width: 100%" />
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

.imei-text {
  font-family: monospace;
  font-size: 12px;
  color: #555;
}
</style>
