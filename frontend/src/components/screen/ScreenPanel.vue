<!-- 大屏通用面板容器：深色玻璃 + 蓝色发光边框 -->
<script setup lang="ts">
import { useSlots } from 'vue'
defineProps<{ title: string }>()
const slots = useSlots()
</script>

<template>
  <div class="s-panel">
    <div class="s-panel-header">
      <span class="s-panel-corner tl" />
      <span class="s-panel-corner tr" />
      <!-- 标题始终横排，单独占满一行 -->
      <div class="s-panel-title-row">
        <span class="s-panel-title">{{ title }}</span>
      </div>
      <!-- 日期选择器等额外内容另起一行右对齐（有内容时才渲染） -->
      <div v-if="slots['header-extra']" class="s-panel-extra">
        <slot name="header-extra" />
      </div>
    </div>
    <div class="s-panel-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.s-panel {
  background: rgba(0, 20, 60, 0.7);
  border: 1px solid rgba(0, 180, 255, 0.2);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  box-shadow: 0 0 16px rgba(0, 120, 255, 0.1) inset,
              0 2px 12px rgba(0, 0, 0, 0.4);
}

.s-panel-header {
  position: relative;
  padding: 9px 12px 7px;
  border-bottom: 1px solid rgba(0, 180, 255, 0.15);
  background: linear-gradient(90deg, rgba(0, 100, 200, 0.25) 0%, transparent 60%);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.s-panel-corner {
  position: absolute;
  width: 8px; height: 8px;
  border-color: #00d4ff;
  border-style: solid;
}
.s-panel-corner.tl { top: 0; left: 0; border-width: 2px 0 0 2px; }
.s-panel-corner.tr { top: 0; right: 0; border-width: 2px 2px 0 0; }

.s-panel-title-row {
  display: flex;
  align-items: center;
  width: 100%;
}

.s-panel-title {
  font-size: 12px;
  font-weight: 600;
  color: #7dd3fc;
  letter-spacing: 1px;
  white-space: nowrap;
}

/* 额外内容（日期选择器）右对齐 */
.s-panel-extra {
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.s-panel-body {
  flex: 1;
  overflow: hidden;
  padding: 8px;
}
</style>
