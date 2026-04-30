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
}
</style>
