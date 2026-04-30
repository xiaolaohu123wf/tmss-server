<script setup lang="ts">
defineOptions({ name: 'FleetsView' })
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { fleetsApi } from '@/api/fleets'
import type { Fleet, FleetCreate } from '@/types'

const fleets = ref<Fleet[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const form = ref<FleetCreate>({ name: '', notes: '' })

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
  form.value = { name: '', notes: '' }
  dialogVisible.value = true
}

function openEdit(fleet: Fleet) {
  editingId.value = fleet.id
  form.value = { name: fleet.name, notes: fleet.notes ?? '' }
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value!.validate()
  if (editingId.value) {
    await fleetsApi.update(editingId.value, form.value)
    ElMessage.success('更新成功')
  } else {
    await fleetsApi.create(form.value)
    ElMessage.success('已创建')
  }
  dialogVisible.value = false
  await loadData()
}

async function handleDelete(fleet: Fleet) {
  await ElMessageBox.confirm(`确认删除车队「${fleet.name}」？删除后相关车辆将失去归属。`, '警告', {
    type: 'warning',
    confirmButtonText: '删除',
    confirmButtonClass: 'el-button--danger',
  })
  await fleetsApi.delete(fleet.id)
  ElMessage.success('已删除')
  await loadData()
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>车队管理</h3>
      <el-button type="primary" :icon="'Plus'" @click="openCreate">新增车队</el-button>
    </div>

    <el-table :data="fleets" v-loading="loading" border stripe>
      <el-table-column label="ID" prop="id" width="70" />
      <el-table-column label="车队名称" prop="name" min-width="160" />
      <el-table-column label="备注" prop="notes" min-width="200" />
      <el-table-column label="创建时间" prop="created_at" width="170" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑车队' : '新增车队'" width="420px" draggable>
      <el-form ref="formRef" :model="form" label-width="80px">
        <el-form-item label="车队名称" prop="name" :rules="[{ required: true, message: '请输入名称' }]">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { background: #fff; border-radius: 8px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h3 { margin: 0; font-size: 16px; font-weight: 600; }
</style>
