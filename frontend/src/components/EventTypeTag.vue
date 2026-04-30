<script setup lang="ts">
import type { EventType } from '@/types'

const props = defineProps<{ type: EventType | string }>()

type TagType = 'danger' | 'warning' | 'info' | 'primary' | 'success' | undefined

const typeMap: Record<string, { label: string; tagType: TagType }> = {
  overspeed:         { label: '超速',     tagType: 'danger'  },
  geofence_violation:{ label: '越界',     tagType: 'warning' },
  oncoming_warn:     { label: '来车提醒', tagType: 'info'    },
  dispatch:          { label: '调度',     tagType: 'primary' },
  ban_violation:     { label: '禁运违规', tagType: 'danger'  },
  zone_entry:        { label: '进入围栏', tagType: 'success' },
  zone_exit:         { label: '离开围栏', tagType: 'warning' },
  device_offline:    { label: '设备离线', tagType: 'info'    },
  unreported_exit:   { label: '未报备离开',tagType: 'danger' },
}

const config = computed(() => typeMap[props.type] ?? { label: props.type, tagType: undefined })
</script>

<template>
  <el-tag :type="config.tagType" size="small">{{ config.label }}</el-tag>
</template>
