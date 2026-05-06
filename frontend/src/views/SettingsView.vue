<script setup lang="ts">
defineOptions({ name: 'SettingsView' })
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { get, post } from '@/api/index'
import { APP_VERSION_TAG } from '@/releaseMeta'

interface BusinessConfig {
  global_speed_limit: number
  park_threshold_min: number
  alert_cooldown_s: number
  hb_timeout_s: number
  loading_min_stay_s: number
  unloading_min_stay_s: number
  weather_city: string
  map_center_lng: number
  map_center_lat: number
  transport_timeout_min: number
}

const config = ref<BusinessConfig>({
  global_speed_limit: 80,
  park_threshold_min: 10,
  alert_cooldown_s: 10,
  hb_timeout_s: 90,
  loading_min_stay_s: 300,
  unloading_min_stay_s: 180,
  weather_city: 'Beijing',
  map_center_lng: 109.4753,
  map_center_lat: 30.2832,
  transport_timeout_min: 30,
})

const loading = ref(false)
const saving = ref(false)
const reanalyzing = ref(false)
const reanalyzeDays = ref(30)
const reanalyzeResult = ref<{ labeled: number; total_checked: number } | null>(null)

const resegmenting = ref(false)
const resegmentDays = ref(7)
const resegmentResult = ref<{ segments_created: number; devices_processed: number } | null>(null)

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

async function handleReanalyze() {
  reanalyzeResult.value = null
  reanalyzing.value = true
  try {
    const res = await post<{ labeled: number; total_checked: number }>(
      `/admin/reanalyze-segments?days=${reanalyzeDays.value}`,
      {},
    )
    reanalyzeResult.value = res
    ElMessage.success(`标注完成：共检查 ${res.total_checked} 条，标注 ${res.labeled} 条`)
  } finally {
    reanalyzing.value = false
  }
}

async function handleResegment() {
  resegmentResult.value = null
  try {
    await ElMessageBox.confirm(
      `将删除最近 ${resegmentDays.value} 天内所有设备的轨迹段并基于原始定位点重建，此操作不可撤销，确认继续？`,
      '危险操作确认',
      { type: 'warning', confirmButtonText: '确认重建', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  resegmenting.value = true
  try {
    const res = await post<{ segments_created: number; devices_processed: number }>(
      `/admin/resegment-history?days=${resegmentDays.value}`,
      {},
    )
    resegmentResult.value = res
    ElMessage.success(`重分割完成：处理 ${res.devices_processed} 台设备，创建 ${res.segments_created} 段`)
  } finally {
    resegmenting.value = false
  }
}

onMounted(loadConfig)
</script>

<template>
  <div class="settings-page">
    <div class="page-header">
      <h3>系统设置</h3>
      <el-tag type="info" effect="plain">前端 {{ APP_VERSION_TAG }}</el-tag>
      <el-tag type="danger" size="small">高危参数 · 保存时需管理员密码二次验证</el-tag>
    </div>

    <el-card class="about-card" header="版本与发布标记" shadow="never">
      <div class="version-line">
        <span class="version-label">软件版本</span>
        <el-tag type="success" size="large">{{ APP_VERSION_TAG }}</el-tag>
        <span class="version-hint">与 frontend/package.json 及仓库 Git 发布 tag 保持一致；新版本发布时请同时修改版本号。</span>
      </div>
    </el-card>

    <el-row :gutter="16">
      <!-- Speed & Alert settings -->
      <el-col :span="12">
        <el-card header="限速、告警与在线检测" shadow="never" v-loading="loading">
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
        <el-card shadow="never" v-loading="loading">
          <template #header>
            <span>轨迹分段与作业识别</span>
            <el-text type="info" size="small" style="margin-left:8px">按优先级从高到低触发</el-text>
          </template>

          <!-- 优先级 1：围栏识别 -->
          <div class="priority-block">
            <div class="priority-header">
              <el-tag type="danger" effect="dark" size="small">优先级 ①</el-tag>
              <span class="priority-title">装 / 卸料围栏识别</span>
            </div>
            <p class="priority-desc">
              车辆进入取土/弃土电子围栏，且在围栏内持续停留时长 ≥ 下方阈值，
              该段轨迹标记为<b>装料</b>或<b>卸料</b>。
              满足此条件时，后续两级阈值对该段<b>不再生效</b>。
            </p>
            <el-form label-width="140px" :model="config">
              <el-form-item label="取土区最短停留 (秒)">
                <el-input-number
                  v-model="config.loading_min_stay_s"
                  :min="0"
                  :max="3600"
                  style="width: 100%"
                />
              </el-form-item>
              <el-form-item label="弃土区最短停留 (秒)">
                <el-input-number
                  v-model="config.unloading_min_stay_s"
                  :min="0"
                  :max="3600"
                  style="width: 100%"
                />
              </el-form-item>
            </el-form>
          </div>

          <el-divider style="margin:12px 0" />

          <!-- 优先级 2：停车时间 -->
          <div class="priority-block">
            <div class="priority-header">
              <el-tag type="warning" effect="dark" size="small">优先级 ②</el-tag>
              <span class="priority-title">停车时间分段</span>
            </div>
            <p class="priority-desc">
              相邻两个 GPS 点时间间隔 ≥ 阈值，则在此处切断轨迹段。
              若切断产生的段<b>不在</b>围栏内，归类为普通驻留段。
              运输超时阈值则限定离开装/卸料区后最长的运输时限。
            </p>
            <el-form label-width="140px" :model="config">
              <el-form-item label="停车分段阈值 (分钟)">
                <el-input-number
                  v-model="config.park_threshold_min"
                  :min="1"
                  :max="60"
                  style="width: 100%"
                />
              </el-form-item>
              <el-form-item label="运输超时阈值 (分钟)">
                <el-input-number
                  v-model="config.transport_timeout_min"
                  :min="0"
                  :max="480"
                  style="width: 100%"
                />
                <div class="field-hint">
                  离开装/卸料区后超过此时长未抵达下一站 → 作业状态置为"未知"。设为 0 禁用。
                </div>
              </el-form-item>
            </el-form>
          </div>

          <el-divider style="margin:12px 0" />

          <!-- 优先级 3：距离兜底 -->
          <div class="priority-block">
            <div class="priority-header">
              <el-tag type="info" effect="dark" size="small">优先级 ③</el-tag>
              <span class="priority-title">距离过滤（前端兜底）</span>
            </div>
            <p class="priority-desc">
              轨迹查询页"隐藏驻留段"开关：累计行驶距离 &lt; 0.3 km 的普通段默认隐藏，
              表示车辆原地停留未熄火。
              <b>已标记装/卸料的段不受此过滤影响，始终显示。</b>
            </p>
          </div>

          <el-divider style="margin:12px 0" />

          <!-- 天气 -->
          <el-form label-width="140px" :model="config">
            <el-form-item label="天气查询城市">
              <el-input v-model="config.weather_city" placeholder="如 Enshi" />
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- Map center settings -->
    <el-card header="地图默认中心点（GCJ-02 火星坐标）" shadow="never" v-loading="loading">
      <el-form label-width="160px" :model="config">
        <el-form-item label="默认经度">
          <el-input-number
            v-model="config.map_center_lng"
            :min="-180"
            :max="180"
            :precision="7"
            :step="0.001"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="默认纬度">
          <el-input-number
            v-model="config.map_center_lat"
            :min="-90"
            :max="90"
            :precision="7"
            :step="0.001"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item>
          <el-text type="info" size="small">
            大屏及历史轨迹页面初始打开时的地图视角中心。坐标可从高德地图右键菜单复制（高德输出的即为 GCJ-02）。
          </el-text>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 历史轨迹分析工具 -->
    <el-card header="历史轨迹分析工具" shadow="never">
      <!-- 轻量标注 -->
      <div class="analysis-section">
        <div class="analysis-title">轻量标注（仅贴标签）</div>
        <el-alert
          type="info"
          :closable="false"
          style="margin-bottom:12px"
          title="按「起终点围栏对」为已有轨迹段重新打标：起=取土区+终=弃土区→装料；起=弃土区+终=取土区→卸料；其他（同侧/均不在围栏）→清除标签。不重建段结构。"
          show-icon
        />
        <el-form label-width="100px" inline>
          <el-form-item label="回溯天数">
            <el-input-number v-model="reanalyzeDays" :min="1" :max="365" />
          </el-form-item>
          <el-form-item>
            <el-button type="warning" :loading="reanalyzing" @click="handleReanalyze">
              开始标注
            </el-button>
          </el-form-item>
        </el-form>
        <el-result
          v-if="reanalyzeResult"
          icon="success"
          :title="`标注完成：${reanalyzeResult.labeled} / ${reanalyzeResult.total_checked} 条`"
          sub-title="刷新轨迹查询页可看到装料/卸料标签"
          style="padding:8px 0"
        />
      </div>

      <el-divider />

      <!-- 全量重分割 -->
      <div class="analysis-section">
        <div class="analysis-title">全量重分割（重建轨迹段）⚠️</div>
        <el-alert
          type="warning"
          :closable="false"
          style="margin-bottom:12px"
          title="按时间间隔重建所有轨迹段（不按围栏边界切），保留完整取土→弃土运输段；再按起终点围栏对打装/卸料标签。适合新增围栏后重分析历史数据。操作不可撤销。"
          show-icon
        />
        <el-form label-width="100px" inline>
          <el-form-item label="回溯天数">
            <el-input-number v-model="resegmentDays" :min="1" :max="90" />
          </el-form-item>
          <el-form-item>
            <el-button type="danger" :loading="resegmenting" @click="handleResegment">
              重建轨迹段
            </el-button>
          </el-form-item>
        </el-form>
        <el-result
          v-if="resegmentResult"
          icon="success"
          :title="`重建完成：${resegmentResult.devices_processed} 台设备，${resegmentResult.segments_created} 条段`"
          sub-title="刷新轨迹查询页查看新分割结果"
          style="padding:8px 0"
        />
      </div>
    </el-card>

    <div class="save-bar">
      <el-button type="primary" :loading="saving" @click="handleSave">保存参数（二次验证）</el-button>
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
  flex-wrap: wrap;
  gap: 10px 12px;
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
}

.about-card {
  border-radius: 8px;
}

.analysis-section {
  padding: 4px 0;
}

.analysis-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
}

.priority-block {
  padding: 4px 0;
}

.priority-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.priority-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.priority-desc {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  margin: 0 0 10px 0;
  padding: 6px 10px;
  background: #f5f7fa;
  border-radius: 4px;
  border-left: 3px solid #dcdfe6;
}

.field-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.5;
}

.version-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 16px;
  font-size: 14px;
  color: #606266;
}

.version-label {
  font-weight: 600;
  color: #303133;
}

.version-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  flex-basis: 100%;
}

@media (min-width: 768px) {
  .version-hint {
    flex-basis: auto;
    max-width: 420px;
  }
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
