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
const errMsg = ref('')

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  errMsg.value = ''
  await formRef.value!.validate()
  try {
    await auth.login(form.username, form.password)
    if (auth.role === 'terminal') {
      errMsg.value = '终端账号无权访问大屏，请使用管理员或车队长账号'
      await auth.logout()
      return
    }
    const redirect = (route.query.redirect as string) || '/screen'
    router.push(redirect)
  } catch {
    errMsg.value = '用户名或密码错误'
  }
}
</script>

<template>
  <div class="screen-login-bg">
    <!-- 动态粒子背景装饰 -->
    <div class="bg-grid"></div>
    <div class="bg-glow top-left"></div>
    <div class="bg-glow bottom-right"></div>

    <div class="login-card">
      <div class="card-header">
        <div class="logo-wrap">
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
            <circle cx="20" cy="20" r="18" fill="url(#scr-g1)" opacity="0.15"/>
            <circle cx="20" cy="20" r="18" stroke="url(#scr-g1)" stroke-width="1.5"/>
            <path d="M12 28 L20 12 L28 28" stroke="#00d4ff" stroke-width="2.5" fill="none" stroke-linejoin="round"/>
            <path d="M14.5 23 H25.5" stroke="#00d4ff" stroke-width="2" stroke-linecap="round"/>
            <defs>
              <linearGradient id="scr-g1" x1="0" y1="0" x2="40" y2="40">
                <stop offset="0%" stop-color="#00d4ff"/>
                <stop offset="100%" stop-color="#1890ff"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
        <h1 class="sys-title">姚家平水利枢纽</h1>
        <h1 class="sys-title">运营监控大屏</h1>
        <p class="sys-sub">Transportation Monitoring Display</p>
      </div>

      <div class="divider"><span>管理员 / 车队长登录</span></div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="'User'"
            size="large"
            class="dark-input"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            show-password
            :prefix-icon="'Lock'"
            size="large"
            class="dark-input"
          />
        </el-form-item>

        <p v-if="errMsg" class="err-msg">{{ errMsg }}</p>

        <el-button
          type="primary"
          size="large"
          :loading="auth.loading"
          class="login-btn"
          @click="handleLogin"
        >
          进入大屏
        </el-button>
      </el-form>

      <div class="back-link" @click="router.push('/login')">
        → 进入系统后台
      </div>
    </div>
  </div>
</template>

<style scoped>
.screen-login-bg {
  min-height: 100dvh;
  background: #050e1f;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
}

.bg-grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(0,212,255,.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,212,255,.05) 1px, transparent 1px);
  background-size: 48px 48px;
  pointer-events: none;
}
.bg-glow {
  position: absolute; width: 480px; height: 480px;
  border-radius: 50%; pointer-events: none; filter: blur(100px);
}
.bg-glow.top-left    { top: -120px; left: -120px; background: rgba(0,100,255,.18); }
.bg-glow.bottom-right{ bottom: -120px; right: -120px; background: rgba(0,212,255,.12); }

.login-card {
  position: relative; z-index: 1;
  width: 400px;
  background: rgba(5,20,50,.85);
  border: 1px solid rgba(0,212,255,.25);
  border-radius: 16px;
  padding: 40px 36px 36px;
  box-shadow: 0 0 60px rgba(0,100,255,.2), 0 0 20px rgba(0,212,255,.1);
  backdrop-filter: blur(12px);
}

.card-header { text-align: center; margin-bottom: 28px; }
.logo-wrap {
  display: inline-flex; align-items: center; justify-content: center;
  width: 72px; height: 72px; border-radius: 50%;
  background: rgba(0,212,255,.08); border: 1px solid rgba(0,212,255,.3);
  margin-bottom: 16px;
  box-shadow: 0 0 20px rgba(0,212,255,.2);
}
.sys-title {
  font-size: 20px; font-weight: 700; color: #e0f4ff;
  margin: 0; line-height: 1.5; letter-spacing: 2px;
}
.sys-sub {
  font-size: 11px; color: rgba(0,212,255,.5); margin-top: 8px;
  letter-spacing: 1px; font-family: 'Segoe UI', Arial, sans-serif;
}

.divider {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 20px; color: rgba(0,212,255,.4); font-size: 12px;
}
.divider::before, .divider::after {
  content: ''; flex: 1; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,212,255,.3), transparent);
}

:deep(.el-form-item) { margin-bottom: 16px; }
:deep(.el-form-item__error) { color: #ff6b6b; }

.dark-input :deep(.el-input__wrapper) {
  background: rgba(0,20,60,.6);
  border: 1px solid rgba(0,212,255,.2);
  box-shadow: none;
}
.dark-input :deep(.el-input__wrapper:hover) { border-color: rgba(0,212,255,.5); }
.dark-input :deep(.el-input__wrapper.is-focus) { border-color: #00d4ff; box-shadow: 0 0 0 2px rgba(0,212,255,.15); }
.dark-input :deep(.el-input__inner) { color: #e0f4ff; }
.dark-input :deep(.el-input__inner::placeholder) { color: rgba(100,160,200,.5); }
.dark-input :deep(.el-input__prefix-icon) { color: rgba(0,212,255,.6); }

.err-msg {
  color: #ff6b6b; font-size: 13px; text-align: center;
  margin: -4px 0 12px; background: rgba(255,60,60,.08);
  border-radius: 6px; padding: 6px 0;
}

.login-btn {
  width: 100%;
  background: linear-gradient(90deg, #0062cc, #00a8e8);
  border: 1px solid rgba(0,212,255,.4);
  font-size: 15px; letter-spacing: 4px; height: 46px;
  border-radius: 8px; margin-top: 4px;
  box-shadow: 0 4px 20px rgba(0,100,200,.4);
  transition: box-shadow .2s, opacity .2s;
}
.login-btn:hover { opacity: .9; box-shadow: 0 4px 30px rgba(0,150,255,.6); }

.back-link {
  text-align: center; margin-top: 20px;
  color: rgba(0,212,255,.4); font-size: 12px; cursor: pointer;
  transition: color .2s;
}
.back-link:hover { color: rgba(0,212,255,.8); }
</style>
