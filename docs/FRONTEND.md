# TMSS 前端设计文档

> 技术栈：**Vue 3 + Vite + TypeScript + Element Plus + 高德地图 JS API 2.0 + ECharts 5**  
> 目录：`tmss-server/frontend/`

## 端口速查

| 服务 | 端口 | 说明 |
|------|------|------|
| tmss-server **HTTP API** | **8900** | FastAPI，前端所有 `/api/*` 均代理到此 |
| tmss-server **TCP** | **8901** | ESP32 设备接入 |
| Vite **开发服务器** | **5173** | 前端开发热更新服务 |
| y100etest 旧服务 | 8080 | 另一个项目，**不是** tmss-server，避免混淆 |

> `.env` 中 `HTTP_PORT=8900 / TCP_PORT=8901` 为权威配置来源。

---

## 一、快速启动

```bash
cd frontend
npm install

# 开发模式（代理到后端 localhost:8900）
bash dev.sh        # 或 npm run dev（需 Node 18+）

# 生产构建
bash dev.sh build
```

> 因系统默认 Node v10 过旧，需用 `bash dev.sh`（自动定位 Node 20）。  
> Vite 开发代理：`/api` → `http://localhost:8900`（tmss-server HTTP 端口）。

### 配置高德地图 Key

在 `index.html` 中替换占位符：

```html
<!-- 替换为高德开放平台申请的 Key -->
window._AMapSecurityConfig = { securityJsCode: '你的安全密钥' }
<script src="...key=你的WebJSKey&..."></script>
```

---

## 二、目录结构

```
frontend/
├── src/
│   ├── api/                   # HTTP 请求模块
│   │   ├── index.ts           # axios 实例 + 统一响应解析（ok/code/message）
│   │   ├── auth.ts            # 登录 / 登出 / 当前用户
│   │   ├── vehicles.ts        # 车辆 CRUD + 绑定；normalizeVehicle 修复 Decimal→number
│   │   ├── devices.ts         # 设备管理 + 指令下发 + 删除
│   │   ├── geoZones.ts        # 围栏 CRUD
│   │   ├── events.ts          # 事件查询（分页）
│   │   ├── tracks.ts          # 轨迹段查询 / 定位点获取 / 管理员删除
│   │   ├── users.ts           # 用户管理（manager only）
│   │   ├── fleets.ts          # 车队管理 + 车队长查看/编辑本队
│   │   └── weather.ts         # 天气信息查询（大屏展示用）
│   │
│   ├── composables/
│   │   ├── useAmap.ts         # 高德地图封装（初始化 / Marker / Polygon / Polyline / 绘制）
│   │   └── useSSE.ts          # SSE 订阅封装（@vueuse/core + JSON 解析 + 自动重连）
│   │
│   ├── components/
│   │   ├── TabBar.vue             # 多标签页组件（keep-alive 路由缓存）
│   │   ├── VehicleStatusTag.vue   # 作业状态 Tag（颜色区分）
│   │   ├── DeviceStatusTag.vue    # 设备在线/离线 Tag
│   │   ├── EventTypeTag.vue       # 事件类型 Tag
│   │   ├── GeoZoneTypeTag.vue     # 围栏类型 Tag
│   │   ├── DeviceOnlineBadge.vue  # 设备在线/离线徽章
│   │   └── screen/DateRangePicker.vue  # 大屏时间范围选择（v1.3.5）
│   │
│   ├── layouts/
│   │   ├── AuthLayout.vue     # 登录页：浅蓝科技渐变背景 + 浮动光晕
│   │   └── MainLayout.vue     # 主布局（深色侧边栏 + 顶栏 + TabBar + 内容区）
│   │
│   ├── router/
│   │   └── index.ts           # vue-router 4 + 权限守卫
│   │
│   ├── stores/
│   │   ├── auth.ts            # 登录态、角色、fleet_id、isManager
│   │   └── tabs.ts            # 多标签页状态（openTab / closeTab / cachedNames）
│   │
│   ├── types/
│   │   └── index.ts           # TS 类型定义（与后端 Pydantic 模型对齐）
│   │                          # VehicleType = 'truck'|'loader'|'passenger_car'|'other'
│   │
│   ├── views/
│   │   ├── LoginView.vue          # 登录页（浅蓝/水滴图标/系统名称）
│   │   ├── DashboardView.vue      # 实时大屏（地图 + SSE + 围栏叠加 + 俯视卡车图标）
│   │   ├── VehiclesView.vue       # 车辆管理（含家用车型/驾驶员姓名）
│   │   ├── DevicesView.vue        # 设备管理（管理员可删除）
│   │   ├── GeoZonesView.vue       # 围栏管理（卫星图层 + 图层切换 + 近24h轨迹叠加）
│   │   ├── EventsView.vue         # 事件查询
│   │   ├── TracksView.vue         # 历史轨迹查询与回放（装/卸料标签 + 围栏叠加 + 管理员删除）
│   │   ├── UsersView.vue          # 用户管理
│   │   ├── FleetsView.vue         # 车队管理（manager only）
│   │   ├── FleetProfileView.vue   # 车队长查看/编辑本队信息（fleet_captain）
│   │   └── SettingsView.vue       # 系统设置（三级阈值 + 地图中心 + 历史重分析工具）
│   │
│   ├── App.vue                # 根组件（scrollbar-gutter 全局样式）
│   └── main.ts                # 入口（注册 Element Plus、Pinia、Router）
│
├── index.html                 # 高德地图 JS API + willReadFrequently canvas 修复
├── vite.config.ts             # Vite + 自动导入 + 代理配置
├── tsconfig.json
└── package.json
```

---

## 三、页面与路由

| 路径 | 组件 | 角色限制 | 主要功能 |
|------|------|----------|----------|
| `/login` | `LoginView` | 全部 | 账号密码登录，Cookie Session |
| `/dashboard` | `DashboardView` | 全部已登录 | 实时地图 + SSE + 在线车辆列表 + 围栏叠加开关 + 俯视卡车方向 |
| `/vehicles` | `VehiclesView` | 全部已登录 | 车辆列表 CRUD + 绑定/解绑设备 + 家用车型 |
| `/devices` | `DevicesView` | 全部已登录 | 设备列表 + 在线状态 + 手动下发指令（manager 可删除）|
| `/geo-zones` | `GeoZonesView` | 全部已登录 | 高德地图绘制多边形 + 围栏 CRUD + 图层切换（默认卫星+路网）|
| `/events` | `EventsView` | 全部已登录 | 事件分页查询（时间/类型/车辆过滤）|
| `/tracks` | `TracksView` | 全部已登录 | 历史轨迹查询 + 装/卸料标签 + 围栏叠加 + 地图回放（manager 可删除段）|
| `/users` | `UsersView` | **manager only** | 用户 CRUD + 角色/车队分配 |
| `/fleets` | `FleetsView` | **manager only** | 车队 CRUD |
| `/fleet-profile` | `FleetProfileView` | **fleet_captain** | 查看本队名称、编辑备注 |
| `/settings` | `SettingsView` | **manager only** | 三级阈值配置 + 地图中心 + 历史重分析工具（**需二次密码验证**）|

### 权限守卫逻辑

```typescript
router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.public) return true  // 登录页放行

  if (!auth.isLoggedIn) {
    const ok = await auth.fetchMe()  // 刷新时从 Cookie 恢复 session
    if (!ok) return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresManager && !auth.isManager) {
    return { name: 'dashboard' }  // 无权限重定向
  }
})
```

---

## 四、API 层

### 统一响应格式

后端所有接口返回 `{ ok: true, data: T }` 或 `{ ok: false, code, message }`。  
`src/api/index.ts` 中拦截器统一处理：

- `ok: false` → 弹出 `ElMessage.error(message)` + reject
- 401/403 → 跳转 `/login`
- 网络错误 → 弹出错误提示

### 使用示例

```typescript
import { vehiclesApi } from '@/api/vehicles'

// 直接使用，已处理错误
const vehicles = await vehiclesApi.list()
await vehiclesApi.create({ license_plate: '粤A12345', vehicle_type: 'truck' })
```

---

## 五、实时推送（SSE）

### 接入方式

```typescript
// src/composables/useSSE.ts
const { lastMessage } = useSSE<VehiclePosition>('/api/stream/locations')

watch(lastMessage, (frame) => {
  if (frame) dashboardStore.updatePosition(frame)
})
```

- 基于 `@vueuse/core` 的 `useEventSource`，自动重连（最多 10 次，3 秒间隔）
- 携带 Cookie（`withCredentials: true`），身份验证由服务端处理
- `manager` 订阅所有车辆；`fleet_captain` 仅接收本车队数据（服务端过滤）

### 大屏数据流

```
后端 EventBus.publish → SSE 流 → useSSE composable
→ screenStore.updatePosition / addAlert
→ ScreenMap Marker 更新 / ElNotification 告警弹窗
```

`ScreenMap` 点击车辆后的高亮轨迹选段规则（v1.3.5）：

1. 优先匹配实时状态对应运输段（`transport_loaded` / `transport_empty`）
2. 若无匹配，选择开放段（`ended_at == null`）
3. 兜底使用最新段（列表首项，`started_at DESC`）
4. 查询点位时透传 `buffer_min`，保证运输段缓冲展示一致

---

## 六、高德地图

### useAmap 封装

```typescript
const {
  map, init, setLayers,
  createMarker, createPolyline,
  createPolygon, removePolygon,
  startDrawPolygon, fitPolygon,
} = useAmap('map-container')

onMounted(() => init([lng, lat]))  // 可传入地图中心点

// 创建车辆 Marker（俯视 SVG，anchor:'center'）
const marker = createMarker([116.39, 39.91], vehicleData)

// 创建围栏 Polygon（color + fillOpacity）
const polygon = createPolygon(coordinates, zoneData, '#1890ff', 0.15)

// 图层切换（标准/卫星/卫星+路网/路况）
setLayers([new AMap.TileLayer.Satellite(), new AMap.TileLayer.RoadNet()])

// 绘制模式（围栏管理页）
startDrawPolygon((path) => {
  form.coordinates = path  // 用户完成绘制后回调
})
```

### 车辆方向指示

大屏 `DashboardView` 的车辆 Marker 使用**俯视（鸟瞰）卡车 SVG**：

- SVG 默认朝北（↑），`transform: rotate(headingDeg)` 随实时方位角旋转
- `headingDeg` 通过最近 trail 中最多回溯 5 步的方位角 `atan2(Δlng, Δlat)` 计算
- 仅在方向变化 > 8° 或作业状态变化时调用 `setContent()`（避免频繁重建 DOM）
- `anchor: 'center'`，车身几何中心精确落在 GPS 坐标点
- 车牌标签绝对定位在 SVG 上方，不随旋转偏移

### 车辆状态颜色

| 作业状态 | 颜色 | 含义 |
|----------|------|------|
| `loading` | 橙色 `#fa8c16` | 装料中 |
| `unloading` | 绿色 `#52c41a` | 卸料中 |
| `transport_loaded` | 红色 `#f5222d` | 重载运输 |
| `transport_empty` | 蓝色 `#1890ff` | 空载运输 |
| `unknown` | 灰色 `#8c8c8c` | 未知 |

---

## 七、系统设置二次验证

`/settings` 页面提交前弹出密码确认弹窗，密码通过请求头传递给后端校验：

```typescript
const { value: pw } = await ElMessageBox.prompt('请输入管理员密码确认', '二次验证', {
  inputType: 'password',
})

await post('/admin/config', config.value, {
  headers: { 'X-Confirm-Password': pw },
})
```

后端 `require_password_confirm` 依赖注入器从 `X-Confirm-Password` Header 读取密码并 bcrypt 校验。

---

## 八、开发里程碑

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 项目骨架 + 路由 + Pinia + axios + 登录页 | ✅ 完成 |
| P2 | 主布局 + 车辆管理 + 设备管理 | ✅ 完成 |
| P3 | 围栏管理（含地图绘制）+ 事件查询 | ✅ 完成 |
| P4 | 用户管理 + 车队管理 + 系统设置 | ✅ 完成 |
| P5 | 实时大屏（地图 + SSE + 告警）| ✅ 完成 |
| P6 | 历史轨迹查询（AMap Polyline + 回放 + GCJ-02 + 管理员删除）| ✅ 完成 |
| P7 | SSE 联调 + TabBar 多标签页 + 性能优化 | ✅ 完成 |
| P8 | 登录页重设计（科技蓝主题 + 水滴图标 + 系统名称）| ✅ 完成 |
| P9 | 装/卸料段标注 + 驻留段过滤 + 跳变断线 + 轨迹页围栏叠加 | ✅ 完成 |
| P10 | 大屏围栏叠加开关 + 俯视卡车方向指示 + 图层切换 | ✅ 完成 |
| P11 | 系统设置三级阈值说明 + 历史重分析工具 + 运输超时配置 | ✅ 完成 |
| P12 | 系统更名为"姚家平车辆智能监管平台" | ✅ 完成 |
| P13 | 大屏日期筛选联动 + 轨迹高亮纠偏（v1.3.5） | ✅ 完成 |

---

## 九、待完善事项

1. **ECharts 统计面板**：大屏右侧增加作业状态分布饼图、今日告警趋势折线图
2. **围栏管理地图坐标同步**：编辑已有围栏时，在地图上高亮显示当前围栏并支持拖拽修改顶点
3. **nginx 配置**：✅ 已完成，`nginx.conf` 位于项目根目录，生产部署时执行 `cp nginx.conf /etc/nginx/conf.d/tmss.conf && nginx -s reload`
4. **SSE 前端对接完善**：测试多设备并发下 SSE 断线重连后车辆位置的一致性
5. **历史轨迹 ECharts 速度图**：`TracksView` 底部增加速度折线图，与时间轴联动
6. **车队长权限 V2**：见 `FEATURE_FLEET_CAPTAIN_V2.md`，包含大屏拖影、设备绑定车队隔离等（待确认后开发）
