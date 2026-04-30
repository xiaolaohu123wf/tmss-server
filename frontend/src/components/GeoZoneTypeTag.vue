<script setup lang="ts">
import type { GeoZoneType } from '@/types'

const props = defineProps<{ type: GeoZoneType | string }>()

type TagType = 'success' | 'warning' | 'danger' | 'info' | 'primary' | undefined

const typeMap: Record<string, { label: string; tagType: TagType }> = {
  loading:       { label: '装料区',  tagType: 'success'  },
  unloading:     { label: '卸料区',  tagType: 'warning'  },
  restricted:    { label: '限行区',  tagType: 'danger'   },
  sharp_curve:   { label: '急弯区',  tagType: 'info'     },
  single_bridge: { label: '单边桥',  tagType: 'info'     },
  speed_zone:    { label: '限速区',  tagType: 'primary'  },
}

const config = computed(() => typeMap[props.type] ?? { label: props.type, tagType: undefined })
</script>

<template>
  <el-tag :type="config.tagType" size="small">{{ config.label }}</el-tag>
</template>
