<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref<FormInstance>()
const form = reactive({ username: '', password: '' })

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  await formRef.value!.validate()
  await auth.login(form.username, form.password)
  const redirect = (route.query.redirect as string) || '/dashboard'
  router.push(redirect)
}
</script>

<template>
  <div class="login-wrapper">
    <div class="login-card">
      <!-- 顶部蓝色装饰条 -->
      <div class="card-top-bar"></div>

      <div class="card-body">
        <!-- 图标 + 标题 -->
        <div class="login-header">
          <div class="icon-ring">
            <!-- 水利枢纽主题：水滴 + 内部波浪 -->
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 3 C18 3 5 17 5 24 A13 13 0 0 0 31 24 C31 17 18 3 18 3Z" fill="url(#drop-grad)"/>
              <path d="M11 25 Q14 21 18 25 Q22 29 25 25" stroke="white" stroke-width="2" fill="none" stroke-linecap="round"/>
              <defs>
                <linearGradient id="drop-grad" x1="18" y1="3" x2="18" y2="37" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stop-color="#38bdf8"/>
                  <stop offset="100%" stop-color="#0284c7"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h1 class="sys-title">姚家坪水利枢纽</h1>
          <h1 class="sys-title">土方运输智能管控系统</h1>
          <p class="sys-subtitle">Truck Monitoring System Simplify</p>
        </div>

        <!-- 分割线 -->
        <div class="divider"><span>用户登录</span></div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          @keyup.enter="handleLogin"
        >
          <el-form-item label="用户名" prop="username">
            <el-input
              v-model="form.username"
              placeholder="请输入用户名"
              :prefix-icon="'User'"
              size="large"
            />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              show-password
              :prefix-icon="'Lock'"
              size="large"
            />
          </el-form-item>

          <el-form-item style="margin-top: 8px">
            <el-button
              type="primary"
              size="large"
              :loading="auth.loading"
              class="login-btn"
              @click="handleLogin"
            >
              登 录
            </el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-wrapper {
  width: 100%;
  display: flex;
  justify-content: center;
  position: relative;
  z-index: 1;
}

/* 卡片整体 */
.login-card {
  width: 440px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  box-shadow:
    0 4px 24px rgba(14, 165, 233, 0.15),
    0 1px 6px rgba(14, 165, 233, 0.08);
  border: 1px solid rgba(186, 230, 253, 0.6);
  overflow: hidden;
}

/* 顶部蓝色装饰条 */
.card-top-bar {
  height: 4px;
  background: linear-gradient(90deg, #0ea5e9 0%, #38bdf8 50%, #7dd3fc 100%);
}

.card-body {
  padding: 36px 40px 40px;
}

/* 标题区 */
.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.icon-ring {
  width: 68px;
  height: 68px;
  border-radius: 50%;
  background: linear-gradient(135deg, #e0f2fe, #bae6fd);
  border: 2px solid rgba(14, 165, 233, 0.3);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  box-shadow: 0 0 0 6px rgba(14, 165, 233, 0.08);
}

.sys-title {
  font-size: 20px;
  font-weight: 700;
  color: #0c4a6e;
  margin: 0;
  line-height: 1.5;
  letter-spacing: 1px;
}

.sys-subtitle {
  font-size: 12px;
  color: #7eb8d5;
  margin: 8px 0 0;
  letter-spacing: 0.5px;
  font-family: 'Segoe UI', Arial, sans-serif;
}

/* 分割线 */
.divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  color: #94bfcf;
  font-size: 13px;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, #bae6fd, transparent);
}

/* 表单标签颜色 */
:deep(.el-form-item__label) {
  color: #0c4a6e;
  font-weight: 500;
}

/* Input 聚焦边框颜色继承主题，无需额外覆盖 */

/* 登录按钮 */
.login-btn {
  width: 100%;
  background: linear-gradient(90deg, #0ea5e9 0%, #38bdf8 100%);
  border: none;
  font-size: 16px;
  letter-spacing: 4px;
  height: 44px;
  border-radius: 8px;
  transition: opacity 0.2s, box-shadow 0.2s;
}

.login-btn:hover {
  opacity: 0.9;
  box-shadow: 0 4px 16px rgba(14, 165, 233, 0.4);
}
</style>
