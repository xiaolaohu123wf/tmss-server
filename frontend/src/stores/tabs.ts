import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

export interface TabItem {
  name: string   // route.name (用于 keep-alive)
  path: string   // route.path (用于导航)
  title: string
  closable: boolean
}

// 首页标签（不可关闭）
const HOME_TAB: TabItem = {
  name: 'dashboard',
  path: '/dashboard',
  title: '主页面',
  closable: false,
}

export const useTabsStore = defineStore('tabs', () => {
  const tabs = ref<TabItem[]>([HOME_TAB])
  const activeTabName = ref<string>('dashboard')

  const cachedNames = computed(() => tabs.value.map((t) => t.name))

  function openTab(route: RouteLocationNormalizedLoaded) {
    const name = route.name as string
    const title = (route.meta.title as string) ?? name
    const path = route.path

    if (!tabs.value.find((t) => t.name === name)) {
      tabs.value.push({ name, path, title, closable: true })
    }
    activeTabName.value = name
  }

  /** 关闭 tab，返回需要跳转的目标 path（若关闭的是当前页则切到相邻 tab）*/
  function closeTab(name: string): string | null {
    const idx = tabs.value.findIndex((t) => t.name === name)
    if (idx === -1) return null

    tabs.value.splice(idx, 1)

    // 如果关闭的是当前激活 tab，切换到相邻 tab
    if (activeTabName.value === name) {
      const next = tabs.value[Math.min(idx, tabs.value.length - 1)]
      activeTabName.value = next.name
      return next.path
    }
    return null
  }

  function closeOtherTabs(name: string) {
    tabs.value = tabs.value.filter((t) => !t.closable || t.name === name)
    activeTabName.value = name
  }

  function closeAllTabs() {
    tabs.value = [HOME_TAB]
    activeTabName.value = 'dashboard'
  }

  return {
    tabs,
    activeTabName,
    cachedNames,
    openTab,
    closeTab,
    closeOtherTabs,
    closeAllTabs,
  }
})
