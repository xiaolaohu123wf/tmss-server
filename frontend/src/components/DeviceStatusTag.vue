<script setup lang="ts">
import { computed } from 'vue'
import type { Device } from '@/types'

/**
 * 设备综合状态标签
 *
 * 状态由 online + last_loc_type 两字段派生：
 *   离线         : online=false
 *   在线·未定位  : online=true, last_loc_type=null
 *   基站定位     : online=true, last_loc_type='lbs'   (GPS 未锁定，仅 LBS)
 *   基站+GPS定位 : online=true, last_loc_type='gps'   (GPS 已锁定，同时含 LBS)
 *   未知         : 其他兜底
 */

const props = defineProps<{
  device: Pick<Device, 'online' | 'last_loc_type'>
}>()

type StatusKey = 'offline' | 'online_no_loc' | 'lbs' | 'gps' | 'unknown'

interface StatusInfo {
  label: string
  tagType: 'success' | 'warning' | 'info' | 'danger' | undefined
  dotColor: string
  title: string
}

const STATUS_MAP: Record<StatusKey, StatusInfo> = {
  offline:      { label: '离线',       tagType: 'info',    dotColor: '#909399', title: '设备已断开连接' },
  online_no_loc:{ label: '在线·未定位', tagType: 'warning', dotColor: '#e6a23c', title: '设备在线，尚未收到定位数据' },
  lbs:          { label: '基站定位',   tagType: undefined, dotColor: '#409eff', title: 'GPS 未锁定，使用基站（LBS）粗定位' },
  gps:          { label: '基站+GPS',   tagType: 'success', dotColor: '#67c23a', title: 'GPS 已锁定，精确定位（含基站辅助）' },
  unknown:      { label: '未知',        tagType: 'info',    dotColor: '#c0c4cc', title: '状态未知' },
}

const statusKey = computed<StatusKey>(() => {
  if (!props.device.online) return 'offline'
  const loc = props.device.last_loc_type
  if (!loc) return 'online_no_loc'
  if (loc === 'lbs') return 'lbs'
  if (loc === 'gps') return 'gps'
  return 'unknown'
})

const info = computed(() => STATUS_MAP[statusKey.value])
</script>

<template>
  <el-tooltip :content="info.title" placement="top" :show-after="400">
    <el-tag :type="info.tagType" size="small" class="device-status-tag">
      <span class="dot" :style="{ background: info.dotColor }" />
      {{ info.label }}
    </el-tag>
  </el-tooltip>
</template>

<style scoped>
.device-status-tag {
  cursor: default;
}

.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
  flex-shrink: 0;
}
</style>
