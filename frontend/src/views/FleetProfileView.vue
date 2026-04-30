<script setup lang="ts">
defineOptions({ name: 'FleetProfileView' })
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { fleetsApi } from '@/api/fleets'
import type { FleetMe } from '@/types'

const fleet = ref<FleetMe | null>(null)
const loading = ref(false)
const saving = ref(false)
const notes = ref('')

async function loadFleet() {
  loading.value = true
  try {
    fleet.value = await fleetsApi.getMyFleet()
    notes.value = fleet.value?.notes ?? ''
  } finally {
    loading.value = false
  }
}

async function saveNotes() {
  saving.value = true
  try {
    const updated = await fleetsApi.updateMyFleet({ notes: notes.value || null })
    fleet.value = updated
    notes.value = updated.notes ?? ''
    ElMessage.success('备注已更新')
  } finally {
    saving.value = false
  }
}

onMounted(loadFleet)
</script>

<template>
  <div class="fleet-profile-page">
    <div class="page-header">
      <h3>我的车队</h3>
    </div>

    <div v-loading="loading" class="profile-card">
      <template v-if="fleet">
        <el-descriptions :column="1" border size="default">
          <el-descriptions-item label="车队名称">
            <span class="fleet-name">{{ fleet.name }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="车队 ID">{{ fleet.id }}</el-descriptions-item>
        </el-descriptions>

        <div class="notes-section">
          <div class="notes-label">车队备注</div>
          <el-input
            v-model="notes"
            type="textarea"
            :rows="4"
            placeholder="输入车队备注信息（可选）"
            maxlength="500"
            show-word-limit
          />
          <div class="notes-actions">
            <el-button type="primary" :loading="saving" @click="saveNotes">保存备注</el-button>
          </div>
        </div>
      </template>
      <div v-else-if="!loading" class="empty-hint">暂未关联车队信息</div>
    </div>
  </div>
</template>

<style scoped>
.fleet-profile-page {
  max-width: 640px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.profile-card {
  background: #fff;
  border-radius: 8px;
  padding: 24px;
  min-height: 200px;
}

.fleet-name {
  font-size: 15px;
  font-weight: 600;
  color: #1677ff;
}

.notes-section {
  margin-top: 24px;
}

.notes-label {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
  margin-bottom: 8px;
}

.notes-actions {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.empty-hint {
  text-align: center;
  color: #909399;
  padding: 40px;
}
</style>
