<!-- 大屏共用时间选择控件，放在面板 header-extra 插槽里 -->
<script setup lang="ts">
import { computed } from 'vue'
import { useScreenStore } from '@/stores/screen'

const screen = useScreenStore()

// el-date-picker 需要 [string, string]，value-format="YYYY-MM-DD"
const range = computed({
  get: () => screen.dateRange,
  set: (val) => {
    if (val && val[0] && val[1]) {
      screen.setDateRange(val[0], val[1])
    }
  },
})
</script>

<template>
  <el-date-picker
    v-model="range"
    type="daterange"
    size="small"
    :clearable="false"
    value-format="YYYY-MM-DD"
    start-placeholder="起始"
    end-placeholder="截止"
    popper-class="screen-date-picker"
    class="screen-dp"
  />
</template>

<style scoped>
.screen-dp {
  width: 178px !important;
}
/* 输入框暗色 */
.screen-dp :deep(.el-input__wrapper) {
  background: rgba(0, 20, 60, 0.7) !important;
  box-shadow: 0 0 0 1px rgba(0, 180, 255, 0.3) inset !important;
  border-radius: 4px;
}
.screen-dp :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px rgba(0, 212, 255, 0.5) inset !important;
}
.screen-dp :deep(.el-range-input) {
  color: #a8d4f0 !important;
  font-size: 11px !important;
  background: transparent !important;
}
.screen-dp :deep(.el-range-separator) {
  color: rgba(0, 180, 255, 0.5) !important;
}
.screen-dp :deep(.el-range__icon),
.screen-dp :deep(.el-range__close-icon) {
  color: rgba(0, 180, 255, 0.5) !important;
}
</style>
