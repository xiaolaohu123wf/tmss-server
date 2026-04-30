<script setup lang="ts">
const props = defineProps<{ online: boolean | undefined }>()
</script>

<template>
  <el-tag
    :type="props.online ? 'success' : 'info'"
    size="small"
  >
    <span class="dot" :class="{ online: props.online }" />
    {{ props.online ? '在线' : '离线' }}
  </el-tag>
</template>

<style scoped>
.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #909399;
  margin-right: 4px;
  vertical-align: middle;
}
.dot.online {
  background: #67c23a;
}
</style>
