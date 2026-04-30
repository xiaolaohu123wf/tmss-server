<script setup lang="ts">
defineOptions({ name: 'SettingsView' })
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { get, post } from '@/api/index'

interface BusinessConfig {
  global_speed_limit: number
  park_threshold_min: number
  alert_cooldown_s: number
  hb_timeout_s: number
  loading_min_stay_s: number
  unloading_min_stay_s: number
  weather_city: string
}

const config = ref<BusinessConfig>({
  global_speed_limit: 80,
  park_threshold_min: 10,
  alert_cooldown_s: 10,
  hb_timeout_s: 90,
  loading_min_stay_s: 300,
  unloading_min_stay_s: 180,
  weather_city: 'Beijing',
})

const loading = ref(false)
const saving = ref(false)

async function loadConfig() {
  loading.value = true
  try {
    const data = await get<BusinessConfig>('/admin/config')
    config.value = data
  } catch {
    /* 拦截器已提示；保留表单默认值，避免 mounted 未捕获的 Promise */
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  // Require manager password confirmation for high-risk settings change
  let pw: string
  try {
    const { value } = await ElMessageBox.prompt(
      '系统设置为高危操作，请输入管理员密码确认',
      '二次验证',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        inputType: 'password',
        inputPlaceholder: '请输入密码',
        inputValidator: (v) => (v ? true : '密码不能为空'),
      },
    )
    pw = value
  } catch {
    return // user cancelled
  }

  saving.value = true
  try {
    await post('/admin/config', config.value, {
      headers: { 'X-Confirm-Password': pw },
    })
    ElMessage.success('设置已保存')
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<template>
  <div class="settings-page">
    <div class="page-header">
      <h3>系统设置</h3>
      <el-tag type="danger" size="small">高危操作 · 需二次密码验证</el-tag>
    </div>

    <el-row :gutter="16">
      <!-- Speed & Alert settings -->
      <el-col :span="12">
        <el-card header="告警参数" shadow="never" v-loading="loading">
          <el-form label-width="160px" :model="config">
            <el-form-item label="全局限速 (km/h)">
              <el-input-number
                v-model="config.global_speed_limit"
                :min="10"
                :max="200"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="告警防抖冷却 (秒)">
              <el-input-number
                v-model="config.alert_cooldown_s"
                :min="1"
                :max="300"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="心跳超时 (秒)">
              <el-input-number
                v-model="config.hb_timeout_s"
                :min="30"
                :max="600"
                style="width: 100%"
              />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- Work state settings -->
      <el-col :span="12">
        <el-card header="作业参数" shadow="never" v-loading="loading">
          <el-form label-width="160px" :model="config">
            <el-form-item label="停车分段阈值 (分钟)">
              <el-input-number
                v-model="config.park_threshold_min"
                :min="1"
                :max="60"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="装料最短驻留 (秒)">
              <el-input-number
                v-model="config.loading_min_stay_s"
                :min="0"
                :max="3600"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="卸料最短驻留 (秒)">
              <el-input-number
                v-model="config.unloading_min_stay_s"
                :min="0"
                :max="3600"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="天气查询城市">
              <el-input v-model="config.weather_city" placeholder="如 Beijing" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <div class="save-bar">
      <el-button type="primary" :loading="saving" @click="handleSave">
        保存设置（需二次验证）
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
}

.page-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.save-bar {
  display: flex;
  justify-content: flex-end;
  padding: 12px 0;
}
</style>
