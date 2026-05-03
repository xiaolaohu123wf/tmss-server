<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import { ElMessageBox } from 'element-plus'
import TabBar from '@/components/TabBar.vue'
import { getWeather } from '@/api/weather'
import type { WeatherData } from '@/api/weather'

const auth = useAuthStore()
const tabsStore = useTabsStore()
const route = useRoute()
const router = useRouter()
const isCollapse = ref(false)
const mobileDrawerOpen = ref(false)

// ── 响应式：检测手机端 ──────────────────────────────────────
const isMobile = ref(window.innerWidth <= 768)
function onResize() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) mobileDrawerOpen.value = false
}
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))

// ── 天气 ────────────────────────────────────────────────────
const weather = ref<WeatherData | null>(null)
const WEATHER_ICONS: Record<number, string> = {
  0: '☀️', 1: '⛅', 2: '☁️', 3: '🌦', 4: '🌧', 5: '🌨', 6: '🌫', 7: '⛈',
}
const weatherIcon = computed(() =>
  weather.value !== null ? (WEATHER_ICONS[weather.value.code] ?? '🌡️') : '',
)
async function fetchWeather() {
  weather.value = await getWeather()
}
let weatherTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  fetchWeather()
  weatherTimer = setInterval(fetchWeather, 10 * 60 * 1000)
})
onUnmounted(() => { if (weatherTimer) clearInterval(weatherTimer) })

// ── 路由监听 → 标签栏 ────────────────────────────────────────
watch(
  () => route.name,
  () => {
    if (route.name && route.meta.layout !== 'auth') tabsStore.openTab(route)
    mobileDrawerOpen.value = false // 导航后关闭抽屉
  },
  { immediate: true },
)

// ── 菜单数据 ─────────────────────────────────────────────────
const allMenuItems = computed(() => {
  const items = [
    { name: 'dashboard',  path: '/dashboard',  icon: 'Monitor',       label: '大屏' },
    { name: 'vehicles',   path: '/vehicles',   icon: 'Van',           label: '车辆' },
    { name: 'devices',    path: '/devices',    icon: 'Cellphone',     label: '设备' },
    { name: 'geoZones',   path: '/geo-zones',  icon: 'MapLocation',   label: '围栏' },
    { name: 'events',     path: '/events',     icon: 'Bell',          label: '告警' },
    { name: 'tracks',     path: '/tracks',     icon: 'Guide',         label: '轨迹' },
  ]
  if (auth.isManager) {
    items.push(
      { name: 'users',    path: '/users',      icon: 'User',          label: '用户' },
      { name: 'fleets',   path: '/fleets',     icon: 'OfficeBuilding', label: '车队' },
      { name: 'settings', path: '/settings',   icon: 'Setting',       label: '设置' },
    )
  }
  return items
})

// 底部导航只显示最重要的 4 项 + "更多" 抽屉
const bottomNavItems = computed(() => allMenuItems.value.slice(0, 4))
const drawerItems = computed(() => allMenuItems.value.slice(4))

const activeMenu = computed(() => route.path)

const roleLabel = computed(() => {
  const map: Record<string, string> = { manager: '管理者', fleet_captain: '车队长', terminal: '终端' }
  return map[auth.role ?? ''] ?? ''
})

async function handleLogout() {
  await ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning', lockScroll: false })
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="layout-container">

    <!-- ══════════════════ PC 侧边栏（手机隐藏）══════════════════ -->
    <el-aside
      v-if="!isMobile"
      :width="isCollapse ? '64px' : '220px'"
      class="layout-aside"
    >
      <div class="logo" :class="{ collapsed: isCollapse }">
        <el-icon size="24"><Monitor /></el-icon>
        <span v-if="!isCollapse" class="logo-text">TMSS</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :active-text-color="'#1890ff'"
        :collapse="isCollapse"
        :collapse-transition="false"
        class="aside-menu"
      >
        <el-menu-item
          v-for="item in allMenuItems"
          :key="item.name"
          :index="item.path"
          @click="router.push(item.path)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>

      <div class="collapse-btn" @click="isCollapse = !isCollapse">
        <el-icon><component :is="isCollapse ? 'Expand' : 'Fold'" /></el-icon>
      </div>
    </el-aside>

    <!-- ══════════════════ 右侧主区域 ══════════════════ -->
    <el-container direction="vertical" style="min-width:0">

      <!-- ── 顶栏 ────────────────────────────────────── -->
      <el-header class="layout-header">
        <!-- 手机：汉堡图标（仅当 drawerItems 有内容时显示） -->
        <el-icon
          v-if="isMobile && drawerItems.length"
          class="mobile-menu-btn"
          size="22"
          @click="mobileDrawerOpen = true"
        >
          <Expand />
        </el-icon>

        <div class="header-title" :class="{ 'header-title--mobile': isMobile }">
          {{ isMobile ? 'TMSS 管控系统' : 'TMSS 车辆监控系统' }}
        </div>

        <div class="header-right">
          <!-- 天气（手机上隐藏 name，只留图标+温度） -->
          <div v-if="weather" class="weather-widget">
            <span class="weather-icon">{{ weatherIcon }}</span>
            <span class="weather-temp">{{ weather.temp }}°C</span>
            <span v-if="!isMobile" class="weather-name">{{ weather.name }}</span>
          </div>

          <el-tag :type="auth.isManager ? 'danger' : 'info'" size="small">
            {{ roleLabel }}
          </el-tag>

          <span v-if="!isMobile" class="username">{{ auth.session?.username }}</span>

          <el-button
            v-if="auth.role === 'fleet_captain'"
            link
            type="primary"
            @click="router.push('/fleet-profile')"
          >
            <el-icon><OfficeBuilding /></el-icon>
            <span v-if="!isMobile">我的车队</span>
          </el-button>

          <el-button link @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            <span v-if="!isMobile">退出</span>
          </el-button>
        </div>
      </el-header>

      <!-- PC 标签栏（手机隐藏） -->
      <TabBar v-if="!isMobile" />

      <!-- 页面内容 -->
      <el-main class="layout-main" :class="{ 'layout-main--mobile': isMobile }">
        <RouterView v-slot="{ Component, route: r }">
          <keep-alive :include="tabsStore.cachedNames">
            <component :is="Component" :key="r.name as string" />
          </keep-alive>
        </RouterView>
      </el-main>

      <!-- ══════════════════ 手机底部导航栏 ══════════════════ -->
      <nav v-if="isMobile" class="mobile-bottom-nav">
        <button
          v-for="item in bottomNavItems"
          :key="item.name"
          class="mobile-nav-item"
          :class="{ 'mobile-nav-item--active': route.path === item.path }"
          @click="router.push(item.path)"
        >
          <el-icon size="22"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </button>

        <!-- 更多按钮（当有 drawerItems 时显示） -->
        <button
          v-if="drawerItems.length"
          class="mobile-nav-item"
          :class="{ 'mobile-nav-item--active': mobileDrawerOpen }"
          @click="mobileDrawerOpen = true"
        >
          <el-icon size="22"><More /></el-icon>
          <span>更多</span>
        </button>
      </nav>
    </el-container>

    <!-- ══════════════════ 手机侧滑抽屉（更多菜单）══════════════════ -->
    <el-drawer
      v-if="isMobile"
      v-model="mobileDrawerOpen"
      direction="ltr"
      size="72vw"
      :with-header="false"
      :lock-scroll="false"
    >
      <div class="drawer-header">
        <el-icon size="22" color="#1890ff"><Monitor /></el-icon>
        <span class="drawer-title">TMSS</span>
        <el-tag :type="auth.isManager ? 'danger' : 'info'" size="small" style="margin-left:auto">
          {{ auth.session?.username }}
        </el-tag>
      </div>

      <!-- 已在底栏的常用项 -->
      <div class="drawer-section-label">常用</div>
      <div
        v-for="item in bottomNavItems"
        :key="item.name"
        class="drawer-item"
        :class="{ 'drawer-item--active': route.path === item.path }"
        @click="router.push(item.path)"
      >
        <el-icon size="20"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </div>

      <!-- 更多项 -->
      <template v-if="drawerItems.length">
        <div class="drawer-section-label">管理</div>
        <div
          v-for="item in drawerItems"
          :key="item.name"
          class="drawer-item"
          :class="{ 'drawer-item--active': route.path === item.path }"
          @click="router.push(item.path)"
        >
          <el-icon size="20"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </div>
      </template>

      <!-- 车队长：我的车队 -->
      <template v-if="auth.role === 'fleet_captain'">
        <div class="drawer-section-label">账号</div>
        <div class="drawer-item" @click="router.push('/fleet-profile')">
          <el-icon size="20"><OfficeBuilding /></el-icon>
          <span>我的车队</span>
        </div>
      </template>

      <div style="margin-top:auto;padding:16px">
        <el-button type="danger" plain style="width:100%" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>退出登录
        </el-button>
      </div>
    </el-drawer>

  </el-container>
</template>

<style scoped>
/* ══ 公共 ═══════════════════════════════════════════════════ */
.layout-container {
  height: 100vh;
  overflow: hidden;
}

/* ══ PC 侧边栏 ════════════════════════════════════════════ */
.layout-aside {
  background: #001529;
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
  overflow: hidden;
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
  border-bottom: 1px solid #002140;
  flex-shrink: 0;
}
.logo-text {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 2px;
  white-space: nowrap;
}
.aside-menu {
  flex: 1;
  border-right: none;
  background: #001529;
  --el-menu-bg-color: #001529;
  --el-menu-text-color: #ccc;
  --el-menu-hover-bg-color: #002140;
  --el-menu-active-color: #1890ff;
  overflow-y: auto;
  overflow-x: hidden;
}
.collapse-btn {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ccc;
  cursor: pointer;
  border-top: 1px solid #002140;
  flex-shrink: 0;
}
.collapse-btn:hover { background: #002140; color: #fff; }

/* ══ 顶栏 ════════════════════════════════════════════════ */
.layout-header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 56px;
  flex-shrink: 0;
  gap: 8px;
}
.mobile-menu-btn {
  cursor: pointer;
  color: #555;
  flex-shrink: 0;
}
.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.header-title--mobile { font-size: 14px; }
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.username { font-size: 14px; color: #555; }
.weather-widget {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  background: #f0f7ff;
  border: 1px solid #d0e8ff;
  border-radius: 14px;
  font-size: 12px;
  color: #1677ff;
  white-space: nowrap;
}
.weather-icon { font-size: 14px; }
.weather-temp { font-weight: 600; }
.weather-name { color: #555; }

/* ══ 内容区 ══════════════════════════════════════════════ */
.layout-main {
  background: #f0f2f5;
  overflow-y: auto;
  padding: 20px;
  flex: 1;
  scrollbar-gutter: stable;
}
.layout-main--mobile {
  padding: 12px 8px;
  /* 为底部导航栏留出空间（56px）+ iOS 安全区域 */
  padding-bottom: calc(56px + env(safe-area-inset-bottom, 0px) + 12px);
}

/* ══ 手机底部导航栏 ═══════════════════════════════════════ */
.mobile-bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: calc(56px + env(safe-area-inset-bottom, 0px));
  padding-bottom: env(safe-area-inset-bottom, 0px);
  background: #fff;
  border-top: 1px solid #e8e8e8;
  display: flex;
  align-items: stretch;
  z-index: 1000;
  box-shadow: 0 -2px 12px rgba(0,0,0,0.08);
}
.mobile-nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  background: none;
  border: none;
  cursor: pointer;
  color: #888;
  font-size: 11px;
  padding: 6px 0;
  transition: color 0.2s;
  -webkit-tap-highlight-color: transparent;
}
.mobile-nav-item--active {
  color: #1890ff;
}
.mobile-nav-item--active .el-icon {
  filter: drop-shadow(0 0 4px rgba(24,144,255,0.4));
}

/* ══ 侧滑抽屉内容 ════════════════════════════════════════ */
.drawer-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 16px 16px;
  border-bottom: 1px solid #f0f0f0;
}
.drawer-title {
  font-size: 18px;
  font-weight: 700;
  color: #1890ff;
  letter-spacing: 2px;
}
.drawer-section-label {
  font-size: 11px;
  color: #aaa;
  padding: 12px 16px 4px;
  text-transform: uppercase;
  letter-spacing: 1px;
}
.drawer-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  cursor: pointer;
  color: #333;
  font-size: 15px;
  transition: background 0.15s;
  border-radius: 8px;
  margin: 2px 8px;
}
.drawer-item:active { background: #f0f7ff; }
.drawer-item--active {
  background: #e6f4ff;
  color: #1890ff;
  font-weight: 600;
}
</style>
