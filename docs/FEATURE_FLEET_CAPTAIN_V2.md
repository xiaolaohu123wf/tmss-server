# 权限管理 V2 — 车队管理员功能规格

> **状态**：待确认，确认后再开发  
> **优先级**：高  
> **影响范围**：后端 API × 4 处、前端页面 × 3 处、数据库 × 0（现有表结构已满足）

---

## 背景与目标

当前系统中"车队管理员"（`fleet_captain`）角色虽已定义，但实际上权限管控存在以下缺口：

| 缺口 | 现状 | 目标 |
|------|------|------|
| 车队创建后无配套账号 | 须 admin 手动建账号再分配 | 创建车队时自动生成账号密码并返回给管理员 |
| 车队长无法查看/编辑自己车队 | `GET/PUT /api/admin/fleets` 仅 manager 可访问 | 车队长可读取并编辑本队备注 |
| 设备绑定无车队隔离校验 | 车队长可把设备绑到其他车队的车辆 | 绑定时强校验"设备→车辆→车队"归属 |
| 大屏无轨迹拖影、无车牌标注 | 仅显示点位 Marker | 10s 拖影折线 + 小卡车图标 + 车牌标注 |

---

## 需求 1：创建车队时自动生成车队长账号

### 业务描述

管理员在"车队管理"页面新建车队后，系统同时为该车队创建一个 `fleet_captain` 角色的账号，并在响应中一次性返回初始密码（仅此一次明文可见）。

### 接口变更

**`POST /api/admin/fleets`（修改现有接口）**

请求体（新增 `captain_username` 可选字段）：
```json
{
  "name": "一号车队",
  "notes": "负责北区土方",
  "captain_username": "captain_north"   // 可选；不填则自动生成
}
```

响应（新增 `captain` 字段）：
```json
{
  "ok": true,
  "data": {
    "id": 3,
    "name": "一号车队",
    "notes": "负责北区土方",
    "captain": {
      "username": "captain_north",
      "initial_password": "Fleet@2026#3"   // 仅此一次，不持久化明文
    }
  }
}
```

### 自动生成规则

| 字段 | 规则 |
|------|------|
| `username` | 如不传，使用 `fleet_{fleet_id}`（如 `fleet_3`） |
| `initial_password` | 格式 `Fleet@{年份}#{fleet_id}`（如 `Fleet@2026#3`），可预测方便管理员记录；后续管理员可在用户管理页重置 |

### 事务要求

**车队创建 + 用户创建** 必须在同一数据库事务中完成，任一失败均回滚，保证不出现"有车队无账号"的孤儿数据。

### 前端变更（`FleetsView.vue`）

- 新建车队确认后，弹出"账号已创建"提示卡（`ElMessage` 或专属弹窗），展示用户名和初始密码
- 提示卡带"复制到剪贴板"按钮，关闭后不再显示（密码不存 store）

---

## 需求 2：车队长查看并编辑本队信息

### 业务描述

车队长登录后，在"车队信息"入口（侧边栏或顶栏用户菜单）可查看自己所属车队的名称、备注，并允许编辑**备注**字段（名称由管理员维护）。

### 接口变更

**`GET /api/fleets/me`（新增）**

```
权限：require_fleet_or_above
```

响应：
```json
{
  "ok": true,
  "data": {
    "id": 3,
    "name": "一号车队",
    "notes": "负责北区土方"
  }
}
```

> **manager** 调用此接口返回 `null`（管理员不属于某一车队），前端据此判断是否展示入口。

**`PATCH /api/fleets/me`（新增）**

```
权限：require_fleet_captain（只有 fleet_captain 可编辑，manager 无需此入口）
```

请求体：
```json
{ "notes": "负责北区和西区土方" }
```

响应：同 GET，返回更新后的车队数据。

### 前端变更

- `MainLayout.vue` 顶栏用户菜单：`fleet_captain` 角色显示"我的车队"入口
- 点击跳转至新增页面 `/fleet-profile`（`FleetProfileView.vue`）
  - 展示车队名称（只读）、备注（可编辑）
  - 提交调用 `PATCH /api/fleets/me`

---

## 需求 3：设备绑定的车队隔离与流程规范

### 业务描述

设备上电后自动在 `device` 表注册。**绑定**是指将设备与某辆车关联，关联后该设备的 GPS 数据记录在对应车辆名下。

**约束规则：**

1. 一台设备同时只能绑定一辆车（数据库唯一索引已保证）
2. `fleet_captain` 只能将设备绑定到**本车队的车辆**；绑定前系统校验 `vehicle.fleet_id == session.fleet_id`
3. 设备已被其他车队绑定时，本车队无法绑定，须对方车队长或 manager 先解绑
4. 解绑操作：`fleet_captain` 只能解绑本车队已绑定的设备；`manager` 可解绑任意设备

### 接口变更

**`GET /api/devices`（修改）**

新增查询参数 `unbound=true`，返回**未绑定**的设备列表（含 IMEI、上次在线时间等），供车队长选择绑定目标。

```
GET /api/devices?unbound=true
权限：require_fleet_or_above
```

**`POST /api/devices/{device_id}/bind`（修改，增加车队校验）**

```python
# 伪代码
if session.role == "fleet_captain":
    vehicle = await vehicle_repo.find_by_id(conn, body.vehicle_id)
    if vehicle is None or vehicle.fleet_id != session.fleet_id:
        raise PermissionDeniedError("只能绑定本车队的车辆")
```

**`POST /api/devices/{device_id}/unbind`（修改，增加车队校验）**

```python
if session.role == "fleet_captain":
    current_bind = await device_repo.get_current_bind(conn, device_id)
    if current_bind is None:
        raise NotFoundError("设备未绑定")
    vehicle = await vehicle_repo.find_by_id(conn, current_bind.vehicle_id)
    if vehicle is None or vehicle.fleet_id != session.fleet_id:
        raise PermissionDeniedError("只能解绑本车队的设备")
```

### 前端变更（`DevicesView.vue`、`VehiclesView.vue`）

**DevicesView.vue**
- 新增"未绑定设备"筛选 Tab，显示可绑定列表
- 绑定时弹出下拉框，仅列出**本车队的车辆**（`GET /api/vehicles` 已按 `fleet_id` 过滤）

**VehiclesView.vue**
- 绑定设备按钮旁显示当前已绑定设备的 IMEI；已绑定时显示"解绑"按钮
- 跨车队已绑定的设备显示"已被其他车队绑定"提示，按钮置灰

---

## 需求 4：车队长轨迹查询（已基本完成）

### 当前状态

`GET /api/track-segments` 和 `GET /api/track-segments/{id}/points` 均已按 `fleet_id` 过滤，`fleet_captain` 只能看到本车队车辆的轨迹。

### 待确认事项

- **轨迹查询页面** (`TracksView.vue`) 中的车辆下拉筛选：是否需要展示车辆所属车队名称？（当前仅显示车牌）
- 车队长是否需要导出轨迹数据（CSV/Excel）？（当前版本无此功能）

---

## 需求 5：大屏实时定位优化

### 5.1 数据隔离（已完成）

SSE `GET /api/stream` 已按 `fleet_id` 过滤：
- `manager` → 接收所有车辆位置
- `fleet_captain` → 只接收本车队车辆位置

**无需后端改动。**

### 5.2 轨迹拖影（10s 历史轨迹）

**实现方案：前端内存滑动窗口**

每收到一帧位置更新，将坐标追加到 `Map<vehicleId, GCJ02Point[]>` 中，保留最近 **N 个点**（N 根据 GPS 上报频率 1s/次 × 10s = **10 点**）。

用 `AMap.Polyline` 渲染拖影，颜色随时间衰减（旧点透明度低）：

```typescript
// 实现示意
const TRAIL_MAX = 10

// store 中维护
const trailMap = new Map<number, [number, number][]>()   // vehicleId → 最近10个坐标

function updateTrail(vehicleId: number, lngLat: [number, number]) {
  const trail = trailMap.get(vehicleId) ?? []
  trail.push(lngLat)
  if (trail.length > TRAIL_MAX) trail.shift()
  trailMap.set(vehicleId, trail)
}

// 每次更新位置时同步更新 Polyline
function refreshTrailPolyline(vehicleId: number) {
  const trail = trailMap.get(vehicleId) ?? []
  const polyline = trailPolylineMap.get(vehicleId)
  polyline?.setPath(trail)
}
```

拖影折线样式：
```typescript
new AMap.Polyline({
  path: trail,
  strokeColor: '#1890ff',
  strokeOpacity: 0.6,
  strokeWeight: 3,
  strokeStyle: 'solid',
  lineJoin: 'round',
})
```

### 5.3 小卡车图标 + 车牌标注

**AMap 自定义 Marker 方案：**

使用 `AMap.Marker` 的 `content` 属性（HTML 字符串），将图标与车牌合并为一个 DOM 元素，避免两个叠加层的对齐问题：

```typescript
function makeVehicleContent(licensePlate: string, workState: WorkState): string {
  const color = WORK_STATE_COLOR[workState] ?? '#8c8c8c'
  return `
    <div class="vehicle-marker" style="text-align:center; transform:translate(-50%,-100%)">
      <svg width="28" height="22" viewBox="0 0 28 22" fill="none">
        <!-- 小卡车 SVG（cab + body） -->
        <rect x="1" y="8" width="16" height="10" rx="2" fill="${color}"/>
        <rect x="17" y="11" width="8" height="7" rx="1" fill="${color}"/>
        <circle cx="6"  cy="19" r="2.5" fill="#333"/>
        <circle cx="20" cy="19" r="2.5" fill="#333"/>
        <rect x="2" y="9" width="6" height="5" rx="1" fill="rgba(255,255,255,0.5)"/>
      </svg>
      <div style="
        background:rgba(0,0,0,0.65);color:#fff;
        font-size:11px;padding:1px 4px;border-radius:3px;
        white-space:nowrap;margin-top:2px">
        ${licensePlate}
      </div>
    </div>
  `
}
```

> **待确认**：是否使用现成 SVG 图标文件（如项目 `static/` 目录下放置 `truck.svg`），还是使用上述内联 SVG？内联方案无需额外资源请求，颜色可按作业状态动态改变。

---

## 开放性问题（需确认后再开发）

| # | 问题 | 建议默认 | 影响模块 |
|---|------|---------|---------|
| Q1 | 车队长初始密码是否采用 `Fleet@{年}#{id}` 格式，还是完全随机？ | 建议半随机（`Fleet@{年}#{id}`），便于管理员记忆 | 后端 `router_admin.py` |
| Q2 | 侧边栏是否为车队长新增"车队信息"菜单项，还是放在顶栏用户菜单下拉里？ | 建议顶栏下拉（不占侧边栏空间） | 前端 `MainLayout.vue` |
| Q3 | 车队长能否修改车队**名称**，还是仅可修改**备注**？ | 建议仅备注（名称由管理员维护，防误操作） | 后端 `PATCH /api/fleets/me` |
| Q4 | 拖影点数是否固定 10 点（≈10s），还是可配置（如与心跳超时联动）？ | 建议固定 10 点，简单明确 | 前端 `DashboardView.vue` |
| Q5 | 小卡车图标是内联 SVG（颜色随作业状态变化），还是静态图片文件？ | 建议内联 SVG，动态颜色更直观 | 前端 `DashboardView.vue` |
| Q6 | 车队长是否可删除本车队的轨迹段？（当前仅 manager 可删除） | 建议**否**，删除轨迹属于高权限操作 | 后端 `router_track_segments.py` |
| Q7 | 创建车队的同时是否需要直接录入第一辆车和第一台设备？还是分步操作？ | 建议分步（先建车队，再建车辆，再绑设备） | 前端 `FleetsView.vue` |

---

## 受影响的文件速查

### 后端

| 文件 | 变更类型 | 内容 |
|------|---------|------|
| `app/http/routers/router_admin.py` | 修改 | `POST /api/admin/fleets` 增加自动建账号逻辑 |
| `app/http/routers/router_devices.py` | 修改 | `bind/unbind` 增加 fleet 归属校验；`list` 增加 `unbound` 过滤 |
| `app/http/routers/router_fleets.py` | **新增** | `GET/PATCH /api/fleets/me` |
| `app/http/deps.py` | 微调 | 新增 `require_fleet_captain` 依赖（现有 `require_fleet_or_above` 仍保留） |
| `app/db/queries/device.py` | 修改 | 新增 `SELECT_UNBOUND_DEVICES_SQL` |
| `app/db/queries/fleet.py` | 修改 | 新增 `UPDATE_FLEET_NOTES_SQL` |

### 前端

| 文件 | 变更类型 | 内容 |
|------|---------|------|
| `frontend/src/views/FleetsView.vue` | 修改 | 建队成功后展示初始账号密码 |
| `frontend/src/views/DevicesView.vue` | 修改 | "未绑定设备"筛选；绑定时下拉限本车队车辆 |
| `frontend/src/views/VehiclesView.vue` | 微调 | 显示当前绑定设备 IMEI；跨队绑定状态提示 |
| `frontend/src/views/FleetProfileView.vue` | **新增** | 车队信息查看与备注编辑 |
| `frontend/src/views/DashboardView.vue` | 修改 | 拖影折线；小卡车 SVG Marker + 车牌标注 |
| `frontend/src/layouts/MainLayout.vue` | 微调 | 车队长显示"我的车队"入口 |
| `frontend/src/api/fleets.ts` | 修改 | 新增 `getMyFleet()` 和 `updateMyFleet()` |
| `frontend/src/router/index.ts` | 修改 | 新增 `/fleet-profile` 路由 |

---

## 开发工作量估算

| 模块 | 工作量 |
|------|--------|
| 需求 1（自动建账号） | ~2h |
| 需求 2（车队长查看/编辑车队） | ~2h |
| 需求 3（设备绑定隔离） | ~3h |
| 需求 4（轨迹查询，已基本完成） | ~0.5h（确认项补完） |
| 需求 5（大屏拖影 + 图标）| ~3h |
| **合计** | **~10h** |
