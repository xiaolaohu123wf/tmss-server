<script setup lang="ts">
import type { WorkState } from '@/types'

type TagType = 'success' | 'warning' | 'info' | 'danger' | 'primary' | undefined

const props = defineProps<{ state: WorkState | null | undefined }>()

const stateMap: Record<WorkState, { label: string; type: TagType }> = {
  loading:          { label: '装料中',   type: 'warning' },
  unloading:        { label: '卸料中',   type: 'success' },
  transport_loaded: { label: '重载运输', type: 'danger'  },
  transport_empty:  { label: '空载运输', type: 'info'    },
  unknown:          { label: '未知',     type: undefined },
}

const config = computed(() => {
  if (!props.state) return { label: '未知', type: undefined as TagType }
  return stateMap[props.state] ?? { label: props.state, type: undefined as TagType }
})
</script>

<template>
  <el-tag :type="config.type" size="small">{{ config.label }}</el-tag>
</template>
