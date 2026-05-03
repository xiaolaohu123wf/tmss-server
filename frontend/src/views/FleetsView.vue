<script setup lang="ts">
defineOptions({ name: 'FleetsView' })
import { ref, onMounted } from 'vue'
const isMobile = ref(window.innerWidth <= 768)
onMounted(() => window.addEventListener('resize', () => { isMobile.value = window.innerWidth <= 768 }))
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { fleetsApi } from '@/api/fleets'
import type { Fleet, FleetCreate, FleetCaptainCredentials } from '@/types'
import { formatChinaDateTime } from '@/utils/datetime'

const fleets = ref<Fleet[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = ref<FleetCreate>({ name: '', notes: '', captain_username: '' })

// 创建成功后展示账号弹窗
const credDialogVisible = ref(false)
const newCredentials = ref<FleetCaptainCredentials | null>(null)
const newFleetName = ref('')

async function loadData() {
  loading.value = true
  try {
    fleets.value = await fleetsApi.list()
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

function openCreate() {
  editingId.value = null
  form.value = { name: '', notes: '', captain_username: '' }
  dialogVisible.value = true
}

function openEdit(fleet: Fleet) {
  editingId.value = fleet.id
  form.value = { name: fleet.name, notes: fleet.notes ?? '' }
  dialogVisible.value = true
}

async function handleSubmit() {
  try {
    await formRef.value!.validate()
  } catch {
    return
  }
  if (editingId.value) {
    await fleetsApi.update(editingId.value, { name: form.value.name, notes: form.value.notes })
    ElMessage.success('更新成功')
    dialogVisible.value = false
  } else {
    const result = await fleetsApi.create(form.value)
    dialogVisible.value = false
    // 展示初始账号密码
    newFleetName.value = result.name
    newCredentials.value = result.captain
    credDialogVisible.value = true
  }
  await loadData()
}

async function handleDelete(fleet: Fleet) {
  await ElMessageBox.confirm(`确认删除车队「${fleet.name}」？删除后相关车辆将失去归属。`, '警告', {
    type: 'warning',
    confirmButtonText: '删除',
    confirmButtonClass: 'el-button--danger',
    lockScroll: false,
  })
  await fleetsApi.delete(fleet.id)
  ElMessage.success('已删除')
  await loadData()
}

function copyCredentials() {
  if (!newCredentials.value) return
  const text = `用户名：${newCredentials.value.username}\n密码：${newCredentials.value.initial_password}`
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制到剪贴板'))
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>车队管理</h3>
      <el-button type="primary" :icon="'Plus'" @click="openCreate">新增车队</el-button>
    </div>

    <el-table :data="fleets" v-loading="loading" border stripe>
      <el-table-column v-if="!isMobile" label="ID" prop="id" width="70" />
      <el-table-column label="车队名称" prop="name" min-width="120" />
      <el-table-column v-if="!isMobile" label="备注" prop="notes" min-width="160" />
      <el-table-column v-if="!isMobile" label="创建时间" width="175">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑车队对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑车队' : '新增车队'" :width="isMobile ? '95vw' : '440px'" draggable>
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item label="车队名称" prop="name" :rules="[{ required: true, message: '请输入名称' }]">
          <el-input v-model="form.name" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item v-if="!editingId" label="管理员账号" prop="captain_username">
          <el-input v-model="form.captain_username" placeholder="留空则自动生成 fleet_{id}" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 账号密码展示弹窗（仅新建时显示一次） -->
    <el-dialog
      v-model="credDialogVisible"
      title="车队长账号已创建"
      :width="isMobile ? '95vw' : '400px'"
      :close-on-click-modal="false"
    >
      <p class="cred-tip">车队「<strong>{{ newFleetName }}</strong>」创建成功，初始账号如下，<em>请立即妥善保存</em>：</p>
      <div class="cred-box">
        <div class="cred-row">
          <span class="cred-label">用户名</span>
          <span class="cred-value">{{ newCredentials?.username }}</span>
        </div>
        <div class="cred-row">
          <span class="cred-label">初始密码</span>
          <span class="cred-value mono">{{ newCredentials?.initial_password }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="copyCredentials" type="primary" plain>复制到剪贴板</el-button>
        <el-button type="primary" @click="credDialogVisible = false">我已记录，关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { background: #fff; border-radius: 8px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h3 { margin: 0; font-size: 16px; font-weight: 600; }
@media (max-width: 768px) { .page-container { padding: 12px 8px; border-radius: 0; } }

.cred-tip { margin: 0 0 16px; font-size: 14px; color: #303133; line-height: 1.6; }
.cred-box {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cred-row { display: flex; align-items: center; gap: 12px; }
.cred-label { width: 70px; font-size: 13px; color: #909399; flex-shrink: 0; }
.cred-value { font-size: 15px; font-weight: 600; color: #1d2129; }
.cred-value.mono { font-family: monospace; letter-spacing: 1px; color: #1677ff; }
</style>
