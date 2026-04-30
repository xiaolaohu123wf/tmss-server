import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

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
      meta: { layout: 'main', title: '实时大屏' },
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
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }

  // Manager-only routes
  if (to.meta.requiresManager && !auth.isManager) {
    return { name: 'dashboard' }
  }

  return true
})

export default router
