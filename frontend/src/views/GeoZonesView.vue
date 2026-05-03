<script setup lang="ts">
import { ref, watch, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { geoZonesApi } from '@/api/geoZones'
import { useAmap, type AMapPolygon } from '@/composables/useAmap'
import GeoZoneTypeTag from '@/components/GeoZoneTypeTag.vue'
import type { GeoZone, GeoZoneCreate, GeoZoneType, Coordinate } from '@/types'

defineOptions({ name: 'GeoZonesView' })

// ─── data ────────────────────────────────────────────────────────────────────
const zones = ref<GeoZone[]>([])
const loading = ref(false)

const {
  map,
  init: initMap,
  createPolygon,
  removePolygon,
  updatePolygonColor,
  fitPolygon,
  startDrawPolygon,
} = useAmap('geo-zone-map', { zoom: 14, center: [109.4753, 30.2832] })

// Map from zone.id to its rendered polygon
const polygonMap = new Map<number, AMapPolygon>()
// Currently highlighted polygon (editing)
let highlightPolygon: AMapPolygon | null = null
// Preview polygon drawn by MouseTool (not yet saved)
let previewPolygon: AMapPolygon | null = null
let cancelDrawFn: (() => void) | null = null

// ─── panel state ──────────────────────────────────────────────────────────────
// 'list' = 展示围栏列表, 'form' = 展示编辑表单
const panelMode = ref<'list' | 'form'>('list')
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()
const isDrawing = ref(false)

const emptyForm = (): GeoZoneCreate => ({
  name: '',
  zone_type: 'restricted' as GeoZoneType,
  coordinates: [],
  speed_limit: undefined,
  min_stay_seconds: undefined,
  notes: '',
})
const form = ref<GeoZoneCreate>(emptyForm())

// ─── constants ────────────────────────────────────────────────────────────────
const ZONE_TYPE_OPTIONS = [
  { label: '装料区', value: 'loading' },
  { label: '卸料区', value: 'unloading' },
  { label: '限行区', value: 'restricted' },
  { label: '急弯区', value: 'sharp_curve' },
  { label: '单边桥', value: 'single_bridge' },
  { label: '限速区', value: 'speed_zone' },
]

const ZONE_COLORS: Record<string, string> = {
  loading:       '#52c41a',
  unloading:     '#fa8c16',
  restricted:    '#f5222d',
  sharp_curve:   '#1890ff',
  single_bridge: '#595959',
  speed_zone:    '#722ed1',
}

function zoneColor(type: string) {
  return ZONE_COLORS[type] ?? '#1890ff'
}

// ─── map rendering ────────────────────────────────────────────────────────────
function renderZones() {
  if (!map.value) return
  // remove old polygons
  polygonMap.forEach((p) => removePolygon(p))
  polygonMap.clear()
  highlightPolygon = null

  for (const zone of zones.value) {
    const poly = createPolygon(
      zone.coordinates as Coordinate[],
      zone,
      zoneColor(zone.zone_type),
      zone.is_enabled ? 0.18 : 0.05,
    )
    if (!zone.is_enabled) {
      updatePolygonColor(poly, '#aaa')
    }
    // click polygon → open edit panel (only when NOT drawing)
    ;(poly as unknown as { on: (ev: string, fn: () => void) => void }).on('click', () => {
      if (!isDrawing.value) openEdit(zone)
    })
    polygonMap.set(zone.id, poly)
  }
}

function highlightZone(zone: GeoZone) {
  // Restore previous highlight
  if (highlightPolygon) {
    const z = zones.value.find((z) => z.id === editingId.value)
    if (z) updatePolygonColor(highlightPolygon, zoneColor(z.zone_type))
    highlightPolygon.setOptions?.({ strokeWeight: 2 })
  }
  const poly = polygonMap.get(zone.id)
  if (poly) {
    updatePolygonColor(poly, '#faad14')
    poly.setOptions?.({ strokeWeight: 3, fillOpacity: 0.3 })
    fitPolygon(poly)
    highlightPolygon = poly
  }
}

function restoreHighlight() {
  if (highlightPolygon && editingId.value) {
    const z = zones.value.find((z) => z.id === editingId.value)
    if (z) {
      updatePolygonColor(highlightPolygon, zoneColor(z.zone_type))
      highlightPolygon.setOptions?.({ strokeWeight: 2, fillOpacity: z.is_enabled ? 0.18 : 0.05 })
    }
    highlightPolygon = null
  }
}

// ─── data loading ─────────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    zones.value = await geoZonesApi.list()
    renderZones()
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await nextTick()
  initMap()
  await loadData()
})

// ─── panel actions ────────────────────────────────────────────────────────────
function openCreate() {
  clearPreview()
  restoreHighlight()
  editingId.value = null
  form.value = emptyForm()
  panelMode.value = 'form'
}

function openEdit(zone: GeoZone) {
  clearPreview()
  editingId.value = zone.id
  form.value = {
    name: zone.name,
    zone_type: zone.zone_type,
    coordinates: [...zone.coordinates],
    speed_limit: zone.speed_limit ?? undefined,
    min_stay_seconds: zone.min_stay_seconds ?? undefined,
    notes: zone.notes ?? '',
  }
  highlightZone(zone)
  panelMode.value = 'form'
}

function cancelEdit() {
  clearPreview()
  stopDrawing()
  restoreHighlight()
  panelMode.value = 'list'
}

// ─── drawing ──────────────────────────────────────────────────────────────────
function clearPreview() {
  if (previewPolygon) {
    removePolygon(previewPolygon)
    previewPolygon = null
  }
}

function stopDrawing() {
  cancelDrawFn?.()
  cancelDrawFn = null
  isDrawing.value = false
}

function startDraw() {
  clearPreview()
  isDrawing.value = true
  const color = zoneColor(form.value.zone_type)
  const { cancelDraw } = startDrawPolygon((path, drawn) => {
    form.value.coordinates = path
    previewPolygon = drawn
    // Sync preview color to selected zone type
    updatePolygonColor(drawn, color)
    isDrawing.value = false
    cancelDrawFn = null
    ElMessage.success(`已绘制围栏，共 ${path.length} 个顶点`)
  }, color)
  cancelDrawFn = cancelDraw
}

function cancelDraw() {
  stopDrawing()
  clearPreview()
  form.value.coordinates = []
}

// When zone_type changes, sync preview polygon color
watch(() => form.value.zone_type, (type) => {
  if (previewPolygon) updatePolygonColor(previewPolygon, zoneColor(type))
})

// ─── CRUD ─────────────────────────────────────────────────────────────────────
async function handleSubmit() {
  await formRef.value!.validate()
  if (!form.value.coordinates.length) {
    ElMessage.warning('请先在地图上绘制围栏范围')
    return
  }
  try {
    if (editingId.value) {
      await geoZonesApi.update(editingId.value, form.value)
      ElMessage.success('围栏已更新')
    } else {
      await geoZonesApi.create(form.value)
      ElMessage.success('围栏已创建')
    }
    clearPreview()
    restoreHighlight()
    panelMode.value = 'list'
    await loadData()
  } catch {
    ElMessage.error('保存失败，请重试')
  }
}

async function handleDelete(zone: GeoZone) {
  await ElMessageBox.confirm(`确认删除围栏「${zone.name}」？`, '警告', { type: 'warning' })
  await geoZonesApi.delete(zone.id)
  ElMessage.success('已删除')
  if (editingId.value === zone.id) cancelEdit()
  await loadData()
}

async function handleToggle(zone: GeoZone) {
  await geoZonesApi.toggle(zone.id, !zone.is_enabled)
  await loadData()
}
</script>

<template>
  <div class="geo-zones-page">
    <!-- ───── Map ───── -->
    <div class="map-panel">
      <div id="geo-zone-map" class="amap-container" />
      <!-- Drawing tip overlay -->
      <transition name="fade">
        <div v-if="isDrawing" class="draw-tip">
          <el-icon><i class="el-icon-edit" /></el-icon>
          在地图上依次点击绘制围栏顶点，双击完成绘制
          <el-button size="small" type="danger" plain @click="cancelDraw" style="margin-left:12px">
            取消绘制
          </el-button>
        </div>
      </transition>
    </div>

    <!-- ───── Right panel ───── -->
    <div class="side-panel">

      <!-- LIST mode -->
      <template v-if="panelMode === 'list'">
        <div class="panel-header">
          <span class="panel-title">电子围栏清单</span>
          <el-button type="primary" size="small" @click="openCreate">
            + 新增围栏
          </el-button>
        </div>

        <el-table
          :data="zones"
          v-loading="loading"
          size="small"
          class="zone-table"
          highlight-current-row
          @row-click="(row: GeoZone) => { if (!isDrawing) { highlightZone(row); const p = polygonMap.get(row.id); if (p) fitPolygon(p) } }"
        >
          <el-table-column label="名称" prop="name" min-width="90" show-overflow-tooltip />
          <el-table-column label="类型" width="80">
            <template #default="{ row }">
              <GeoZoneTypeTag :type="row.zone_type" />
            </template>
          </el-table-column>
          <el-table-column label="限速" width="60" align="center">
            <template #default="{ row }">
              {{ row.speed_limit ? `${row.speed_limit}` : '—' }}
            </template>
          </el-table-column>
          <el-table-column label="启用" width="60" align="center">
            <template #default="{ row }">
              <el-switch :model-value="row.is_enabled" @change="handleToggle(row)" @click.stop />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click.stop="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <!-- FORM mode -->
      <template v-else>
        <div class="panel-header">
          <el-button link @click="cancelEdit" class="back-btn">
            ← 返回列表
          </el-button>
          <span class="panel-title">{{ editingId ? '编辑围栏' : '新增围栏' }}</span>
        </div>

        <div class="form-scroll">
          <!-- Draw hint -->
          <el-alert
            v-if="!form.coordinates.length"
            type="info"
            :closable="false"
            style="margin-bottom: 14px"
          >
            <template #default>
              请点击下方「开始绘制」，然后在地图上依次单击顶点，<strong>双击</strong>完成
            </template>
          </el-alert>
          <el-alert
            v-else
            type="success"
            :closable="false"
            style="margin-bottom: 14px"
          >
            <template #default>
              已绘制 {{ form.coordinates.length }} 个顶点
              <el-button link type="primary" size="small" @click="startDraw" style="margin-left:6px">重新绘制</el-button>
            </template>
          </el-alert>

          <!-- Draw button -->
          <div class="draw-row">
            <el-button
              :type="isDrawing ? 'warning' : 'primary'"
              :loading="isDrawing"
              size="default"
              style="width:100%"
              @click="isDrawing ? cancelDraw() : startDraw()"
            >
              {{ isDrawing ? '绘制中… (点击取消)' : (form.coordinates.length ? '重新绘制围栏' : '开始绘制围栏') }}
            </el-button>
          </div>

          <el-divider />

          <el-form ref="formRef" :model="form" label-width="90px" label-position="left">
            <el-form-item
              label="围栏名称"
              prop="name"
              :rules="[{ required: true, message: '请输入围栏名称' }]"
            >
              <el-input v-model="form.name" placeholder="请输入围栏名称" clearable />
            </el-form-item>

            <el-form-item label="围栏类型" prop="zone_type">
              <el-select v-model="form.zone_type" style="width:100%">
                <el-option
                  v-for="o in ZONE_TYPE_OPTIONS"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                >
                  <span
                    class="type-dot"
                    :style="{ background: zoneColor(o.value) }"
                  />
                  {{ o.label }}
                </el-option>
              </el-select>
            </el-form-item>

            <el-form-item label="限速 (km/h)">
              <el-input-number
                v-model="form.speed_limit"
                :min="0"
                :max="200"
                :controls="false"
                placeholder="不限速留空"
                style="width:100%"
              />
            </el-form-item>

            <el-form-item label="最短驻留(s)">
              <el-input-number
                v-model="form.min_stay_seconds"
                :min="0"
                :controls="false"
                placeholder="装/卸料区适用"
                style="width:100%"
              />
            </el-form-item>

            <el-form-item label="备注">
              <el-input v-model="form.notes" type="textarea" :rows="3" placeholder="可选备注" />
            </el-form-item>
          </el-form>
        </div>

        <!-- Footer actions -->
        <div class="form-footer">
          <el-button @click="cancelEdit" style="flex:1">取消</el-button>
          <el-button type="primary" @click="handleSubmit" style="flex:1">保存</el-button>
        </div>
      </template>

    </div>
  </div>
</template>

<style scoped>
.geo-zones-page {
  display: flex;
  gap: 0;
  height: calc(100vh - 116px);
  overflow: hidden;
}

.map-panel {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.amap-container {
  width: 100%;
  height: 100%;
}

/* Drawing tip banner overlaid on map */
.draw-tip {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.72);
  color: #fff;
  padding: 8px 18px;
  border-radius: 20px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 100;
  pointer-events: auto;
  white-space: nowrap;
}

/* Right side panel */
.side-panel {
  width: 400px;
  flex-shrink: 0;
  background: #fff;
  border-left: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.back-btn {
  font-size: 13px;
  color: #606266;
  padding: 0;
}

/* List mode table */
.zone-table {
  flex: 1;
  overflow: hidden;
}
:deep(.zone-table .el-table__body-wrapper) {
  overflow-y: auto;
}

/* Form mode */
.form-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px 16px 4px;
}

.draw-row {
  margin-bottom: 4px;
}

.form-footer {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}

/* Color dot in type selector */
.type-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}

/* Fade animation for draw tip */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
