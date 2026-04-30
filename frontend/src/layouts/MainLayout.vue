<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import { ElMessageBox } from 'element-plus'
import TabBar from '@/components/TabBar.vue'

const auth = useAuthStore()
const tabsStore = useTabsStore()
const route = useRoute()
const router = useRouter()
const isCollapse = ref(false)

// 监听路由变化，自动将当前页加入标签栏
watch(
  () => route.name,
  () => {
    if (route.name && route.meta.layout !== 'auth') {
      tabsStore.openTab(route)
    }
  },
  { immediate: true },
)

const menuItems = computed(() => {
  const items = [
    { name: 'dashboard', path: '/dashboard', icon: 'Monitor', label: '实时大屏' },
    { name: 'vehicles', path: '/vehicles', icon: 'Van', label: '车辆管理' },
    { name: 'devices', path: '/devices', icon: 'Cellphone', label: '设备管理' },
    { name: 'geoZones', path: '/geo-zones', icon: 'MapLocation', label: '围栏管理' },
    { name: 'events', path: '/events', icon: 'Bell', label: '事件查询' },
  ]
  if (auth.isManager) {
    items.push(
      { name: 'users', path: '/users', icon: 'User', label: '用户管理' },
      { name: 'fleets', path: '/fleets', icon: 'OfficeBuilding', label: '车队管理' },
      { name: 'settings', path: '/settings', icon: 'Setting', label: '系统设置' },
    )
  }
  return items
})

// 用路径做 activeMenu，与 el-menu-item 的 index 保持一致
const activeMenu = computed(() => route.path)

const roleLabel = computed(() => {
  const map: Record<string, string> = {
    manager: '管理者',
    fleet_captain: '车队长',
    terminal: '终端用户',
  }
  return map[auth.role ?? ''] ?? ''
})

async function handleLogout() {
  await ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning' })
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="layout-container">
    <!-- ── 侧边栏 ────────────────────────────────── -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="layout-aside">
      <div class="logo" :class="{ collapsed: isCollapse }">
        <el-icon size="24"><Monitor /></el-icon>
        <span v-if="!isCollapse" class="logo-text">TMSS</span>
      </div>

      <!-- 使用 path 作为 index，避免 router 模式与路由名不一致的 active 问题 -->
      <el-menu
        :default-active="activeMenu"
        :active-text-color="'#1890ff'"
        :collapse="isCollapse"
        :collapse-transition="false"
        class="aside-menu"
      >
        <el-menu-item
          v-for="item in menuItems"
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

    <!-- ── 右侧主区域 ──────────────────────────── -->
    <el-container direction="vertical">
      <!-- 顶栏 -->
      <el-header class="layout-header">
        <div class="header-title">TMSS 车辆监控系统</div>
        <div class="header-right">
          <el-tag :type="auth.isManager ? 'danger' : 'info'" size="small">
            {{ roleLabel }}
          </el-tag>
          <span class="username">{{ auth.session?.username }}</span>
          <el-button link @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出
          </el-button>
        </div>
      </el-header>

      <!-- 标签栏 -->
      <TabBar />

      <!-- 页面内容：keep-alive 保留所有已打开标签的状态 -->
      <el-main class="layout-main">
        <RouterView v-slot="{ Component, route: r }">
          <keep-alive :include="tabsStore.cachedNames">
            <component :is="Component" :key="r.name as string" />
          </keep-alive>
        </RouterView>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout-container {
  height: 100vh;
  overflow: hidden;
}

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

.collapse-btn:hover {
  background: #002140;
  color: #fff;
}

.layout-header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 56px;
  flex-shrink: 0;
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.username {
  font-size: 14px;
  color: #555;
}

.layout-main {
  background: #f0f2f5;
  overflow-y: auto;
  padding: 20px;
  flex: 1;
}
</style>
