<script setup lang="ts">
import { useRoute } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import AuthLayout from '@/layouts/AuthLayout.vue'
import ScreenLayout from '@/layouts/ScreenLayout.vue'

const route = useRoute()
</script>

<template>
  <AuthLayout v-if="route.meta.layout === 'auth'" />
  <ScreenLayout v-else-if="route.meta.layout === 'screen'" />
  <MainLayout v-else />
</template>

<!--
  全局基础样式（非 scoped）。
  scrollbar-gutter: stable 让浏览器始终为滚动条预留位置，
  避免 Element Plus Modal/MessageBox 打开时 lock-scroll 补 padding-right
  导致布局宽度变化（地图瓦片抖动、分界线偏移）。
-->
<style>
html {
  scrollbar-gutter: stable;
  /* 手机：使用动态视口高度，避免浏览器地址栏影响布局 */
  height: -webkit-fill-available;
}
body {
  min-height: 100dvh;
  min-height: -webkit-fill-available;
  /* 禁止移动端长按选中文字（地图/按钮操作体验更好） */
  -webkit-user-select: none;
  user-select: none;
}
/* 允许输入框正常选中文字 */
input, textarea { -webkit-user-select: text; user-select: text; }

/* Element Plus 表格、表单等内容区允许选中 */
.el-table, .el-form { -webkit-user-select: text; user-select: text; }

/* ── 手机全局覆盖 ─────────────────────────────────────────── */
@media (max-width: 768px) {
  /* 管理页面通用容器：去掉圆角，充满宽度 */
  .layout-main--mobile .page-container {
    border-radius: 0 !important;
    padding: 12px 8px !important;
  }
  /* page-header 标题缩小 */
  .layout-main--mobile .page-header h3 { font-size: 15px; }
  /* 表格字体缩小一点 */
  .layout-main--mobile .el-table { font-size: 12px; }
  /* dialog 最小宽度保护 */
  .el-dialog { max-width: 96vw !important; }
  /* 分页器折行时对齐 */
  .el-pagination { gap: 4px; }
}
</style>
