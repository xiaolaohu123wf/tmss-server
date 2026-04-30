<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useTabsStore } from '@/stores/tabs'
import { ElDropdown, ElDropdownMenu, ElDropdownItem } from 'element-plus'

const router = useRouter()
const tabsStore = useTabsStore()

function handleTabClick(path: string, name: string) {
  tabsStore.activeTabName = name
  router.push(path)
}

function handleClose(name: string, e: MouseEvent) {
  e.stopPropagation()
  const target = tabsStore.closeTab(name)
  if (target) router.push(target)
}

function handleContextClose(action: string, name: string) {
  if (action === 'others') {
    tabsStore.closeOtherTabs(name)
    // 若当前 active 不在剩余 tabs 里则跳到 name
    const cur = tabsStore.tabs.find((t) => t.name === tabsStore.activeTabName)
    if (!cur) router.push(tabsStore.tabs[0].path)
  } else if (action === 'all') {
    tabsStore.closeAllTabs()
    router.push('/dashboard')
  }
}
</script>

<template>
  <div class="tab-bar">
    <div
      v-for="tab in tabsStore.tabs"
      :key="tab.name"
      class="tab-item"
      :class="{ active: tabsStore.activeTabName === tab.name }"
      @click="handleTabClick(tab.path, tab.name)"
    >
      <!-- 右键菜单 -->
      <el-dropdown
        trigger="contextmenu"
        @command="(cmd: string) => handleContextClose(cmd, tab.name)"
      >
        <span class="tab-title">{{ tab.title }}</span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="others" :disabled="tabsStore.tabs.length <= 1">
              关闭其他标签
            </el-dropdown-item>
            <el-dropdown-item command="all">关闭全部标签</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 关闭按钮 -->
      <span
        v-if="tab.closable"
        class="tab-close"
        @click.stop="handleClose(tab.name, $event)"
      >
        <el-icon size="12"><Close /></el-icon>
      </span>
    </div>
  </div>
</template>

<style scoped>
.tab-bar {
  display: flex;
  align-items: flex-end;
  background: #f0f2f5;
  border-bottom: 1px solid #e8e8e8;
  padding: 0 12px;
  height: 36px;
  flex-shrink: 0;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 4px;

  /* Hide scrollbar but allow scroll */
  scrollbar-width: none;
}

.tab-bar::-webkit-scrollbar {
  display: none;
}

.tab-item {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-bottom: none;
  border-radius: 4px 4px 0 0;
  cursor: pointer;
  white-space: nowrap;
  font-size: 13px;
  color: #555;
  transition: background 0.15s;
  position: relative;
  bottom: -1px;
  flex-shrink: 0;
}

.tab-item:hover {
  color: #1890ff;
  background: #e6f4ff;
}

.tab-item.active {
  color: #1890ff;
  background: #fff;
  border-color: #e8e8e8;
  border-bottom-color: #fff;
  font-weight: 500;
  z-index: 1;
}

.tab-title {
  user-select: none;
}

.tab-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  color: #999;
  flex-shrink: 0;
}

.tab-close:hover {
  background: #ccc;
  color: #333;
}
</style>
