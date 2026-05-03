<script setup lang="ts">
import { useRoute } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import AuthLayout from '@/layouts/AuthLayout.vue'

const route = useRoute()
</script>

<template>
  <AuthLayout v-if="route.meta.layout === 'auth'" />
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
</style>
