import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    layout?: string
    title?: string
    public?: boolean
    requiresManager?: boolean
    /** 大屏路由：terminal 角色不可访问 */
    requiresScreenAccess?: boolean
    /** 去掉 layout-main 的 padding，页面内容贴边显示（用于地图全屏页面） */
    noPadding?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { layout: 'auth', public: true },
    },
    {
      path: '/',
      redirect: '/dashboard',
      meta: { layout: 'main' },
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { layout: 'main', title: '主页面' },
    },
    {
      path: '/vehicles',
      name: 'vehicles',
      component: () => import('@/views/VehiclesView.vue'),
      meta: { layout: 'main', title: '车辆管理' },
    },
    {
      path: '/devices',
      name: 'devices',
      component: () => import('@/views/DevicesView.vue'),
      meta: { layout: 'main', title: '设备管理' },
    },
    {
      path: '/geo-zones',
      name: 'geoZones',
      component: () => import('@/views/GeoZonesView.vue'),
      meta: { layout: 'main', title: '围栏管理' },
    },
    {
      path: '/events',
      name: 'events',
      component: () => import('@/views/EventsView.vue'),
      meta: { layout: 'main', title: '事件查询' },
    },
    {
      path: '/tracks',
      name: 'tracks',
      component: () => import('@/views/TracksView.vue'),
      meta: { layout: 'main', title: '轨迹查询', noPadding: true },
    },
    {
      path: '/history-tasks',
      name: 'historyTasks',
      component: () => import('@/views/HistoryTasksView.vue'),
      meta: { layout: 'main', title: '历史任务查询' },
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('@/views/UsersView.vue'),
      meta: { layout: 'main', title: '用户管理', requiresManager: true },
    },
    {
      path: '/fleets',
      name: 'fleets',
      component: () => import('@/views/FleetsView.vue'),
      meta: { layout: 'main', title: '车队管理', requiresManager: true },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { layout: 'main', title: '系统设置', requiresManager: true },
    },
    {
      path: '/fleet-profile',
      name: 'fleetProfile',
      component: () => import('@/views/FleetProfileView.vue'),
      meta: { layout: 'main', title: '我的车队' },
    },
    // ── 大屏路由 ────────────────────────────────────────────────────
    {
      path: '/screen-login',
      name: 'screenLogin',
      component: () => import('@/views/ScreenLoginView.vue'),
      meta: { layout: 'screen', public: true },
    },
    {
      path: '/screen',
      name: 'screen',
      component: () => import('@/views/ScreenView.vue'),
      meta: { layout: 'screen', title: '运营大屏', requiresScreenAccess: true },
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/dashboard',
    },
  ],
})

// Navigation guard
router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // Public routes (login page) skip auth check
  if (to.meta.public) return true

  // Try to restore session if not yet loaded
  if (!auth.isLoggedIn) {
    const ok = await auth.fetchMe()
    if (!ok) {
      // 大屏路由跳转到大屏登录页
      if (to.meta.requiresScreenAccess) {
        return { name: 'screenLogin', query: { redirect: to.fullPath } }
      }
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }

  // 大屏路由：terminal 角色不可访问
  if (to.meta.requiresScreenAccess && auth.role === 'terminal') {
    return { name: 'screenLogin' }
  }

  // Manager-only routes
  if (to.meta.requiresManager && !auth.isManager) {
    return { name: 'dashboard' }
  }

  return true
})

export default router
