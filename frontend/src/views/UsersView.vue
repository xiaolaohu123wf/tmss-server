<script setup lang="ts">
defineOptions({ name: 'UsersView' })
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { usersApi } from '@/api/users'
import { fleetsApi } from '@/api/fleets'
import type { AppUser, UserCreate, Fleet, UserRole } from '@/types'

const users = ref<AppUser[]>([])
const fleets = ref<Fleet[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const formRef = ref<FormInstance>()
const form = ref<UserCreate>({ username: '', password: '', role: 'fleet_captain' })

const ROLES: { label: string; value: UserRole }[] = [
  { label: '管理者', value: 'manager' },
  { label: '车队长', value: 'fleet_captain' },
]

async function loadData() {
  loading.value = true
  try {
    [users.value, fleets.value] = await Promise.all([usersApi.list(), fleetsApi.list()])
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

async function handleCreate() {
  await formRef.value!.validate()
  await usersApi.create(form.value)
  ElMessage.success('用户已创建')
  dialogVisible.value = false
  await loadData()
}

async function handleDelete(user: AppUser) {
  await ElMessageBox.confirm(`确认删除用户「${user.username}」？`, '警告', { type: 'warning' })
  await usersApi.delete(user.id)
  ElMessage.success('已删除')
  await loadData()
}

const roleLabel = (role: string) => {
  const m: Record<string, string> = { manager: '管理者', fleet_captain: '车队长', terminal: '终端' }
  return m[role] ?? role
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <h3>用户管理</h3>
      <el-button type="primary" :icon="'Plus'" @click="() => { form = { username: '', password: '', role: 'fleet_captain' }; dialogVisible = true }">
        新增用户
      </el-button>
    </div>

    <el-table :data="users" v-loading="loading" border stripe>
      <el-table-column label="ID" prop="id" width="70" />
      <el-table-column label="用户名" prop="username" min-width="120" />
      <el-table-column label="角色" width="100">
        <template #default="{ row }">
          <el-tag :type="row.role === 'manager' ? 'danger' : 'info'" size="small">
            {{ roleLabel(row.role) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="所属车队" prop="fleet_name" min-width="120">
        <template #default="{ row }">
          {{ row.fleet_name ?? '全部' }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '正常' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" prop="created_at" width="170" />
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增用户" width="460px" draggable>
      <el-form ref="formRef" :model="form" label-width="90px">
        <el-form-item label="用户名" prop="username" :rules="[{ required: true }]">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码" prop="password" :rules="[{ required: true, min: 6, message: '至少 6 位' }]">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="r in ROLES" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.role === 'fleet_captain'" label="所属车队" prop="fleet_id">
          <el-select v-model="form.fleet_id" placeholder="请选择车队" style="width: 100%">
            <el-option v-for="f in fleets" :key="f.id" :label="f.name" :value="f.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-container { background: #fff; border-radius: 8px; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h3 { margin: 0; font-size: 16px; font-weight: 600; }
</style>
