# TMSS 开发计划

> **本文档是唯一的任务调度入口。**  
> 功能需求见 `详细说明.md`，架构规范见 `ARCHITECTURE.md`，数据库设计见 `DATABASE.md`，技术栈见 `TECHSTACK.md`。  
> 开发前必须通读以上四份文档。

---

## 文档导航

| 文档 | 职责 |
| --- | --- |
| `详细说明.md` | 功能需求、边缘通讯协议、TCP 指令表 |
| `DATABASE.md` | 建表 SQL、表关系、索引策略 |
| `ARCHITECTURE.md` | **强制规范**：分层规则、命名规范、异常处理、测试规范 |
| `TECHSTACK.md` | 技术选型理由、依赖清单、目录结构 |
| `DEVPLAN.md`（本文） | 开发阶段、任务清单、验收标准 |

---

## 阶段概览

```
阶段 1  地基          ██████████  ✅ 完成    工程骨架 + 数据库迁移 + Core 模块
阶段 2  数据访问层     ██████████  ✅ 完成    DB/Redis 连接池 + 基础 Repo
阶段 3  认证与权限     ██████████  ✅ 完成    Session + 登录/登出 + 依赖注入
阶段 4  HTTP 管理 API  ██████████  ✅ 完成    CRUD 接口 + 数据隔离
阶段 5  TCP 服务基础   ██████████  ✅ 完成    设备接入 + 心跳 + 时间/天气
阶段 6  业务逻辑核心   ██████████  ✅ 完成    超速/围栏/状态机/指令下发
阶段 7  实时推送       ██████████  ✅ 完成    EventBus + SSE 路由
阶段 8  后台任务       ██████████  ✅ 完成    心跳扫描 + 分区自动创建（手动）
阶段 9  前端基础       ██████████  ✅ 完成    Vue 骨架 + 登录 + 管理页
阶段 10 大屏           ██████████  ✅ 完成    高德地图 + SSE + 实时大屏
阶段 11 历史轨迹查询   ██████████  ✅ 完成    轨迹回放 + GCJ-02 转换 + 管理员删除
阶段 12 系统完善       ██████████  ✅ 完成    家用车型 / ICCID 补全 / UI 科技化
```

> **关键依赖链**：阶段 1 → 2 → 3 → 4（并行启动 5）→ 6 → 7 → 8 → 9 → 10 → 11 → 12

---

## 阶段 1：地基 ✅

**目标**：项目可运行，数据库可连接，所有表已建立。

### 任务清单

- [x] `pyproject.toml` — 依赖安装（参考 `TECHSTACK.md §八`）
- [x] `mypy.ini` — strict 模式 + pydantic 插件
- [x] `.pre-commit-config.yaml` — ruff + mypy hooks
- [x] `.env.example` — 列出所有必填环境变量
- [x] `docker-compose.yml` — postgres:16-alpine + redis:7-alpine
- [x] `Dockerfile` — 多阶段构建（参考 `TECHSTACK.md §七`）
- [x] `alembic/` 初始化，`alembic.ini` 配置
- [x] `alembic/versions/V001__init_schema.py` — 完整建表 SQL（来自 `DATABASE.md`，包含全部触发器与索引）
- [x] `app/config.py` — `Settings` 类（参考 `ARCHITECTURE.md §8`）
- [x] `app/core/enums.py` — `WorkState` / `Command` / `UserRole`
- [x] `app/core/exceptions.py` — `TmssError` 异常层级（参考 `ARCHITECTURE.md §5`）
- [x] `app/core/task_registry.py` — `TaskRegistry`（参考 `ARCHITECTURE.md §6`）
- [x] `app/http/response.py` — `ok()` 响应封装
- [x] `app/http/error_handler.py` — 全局异常处理器

### 验收标准

```bash
docker compose up -d
alembic upgrade head          # 无报错，所有表已创建 ✅
python -c "from app.config import settings; print(settings.tcp_port)"
```

---

## 阶段 2：数据访问层 ✅

**目标**：DB 和 Redis 连接池就绪，核心 Repo 可独立集成测试。

### 任务清单

**连接池**
- [x] `app/db/pool.py` — asyncpg Pool 工厂（`get_pool()`）
- [x] `app/db/deps.py` — `get_db_conn`（FastAPI Depends）
- [x] `app/cache/pool.py` — Redis ConnectionPool（`get_redis()`）

**SQL 常量**（`app/db/queries/`）
- [x] `vehicle.py` — SELECT / INSERT / UPDATE / soft-delete SQL
- [x] `device.py` — SELECT by IMEI、UPDATE firmware 等
- [x] `user.py` — SELECT by username、INSERT、password hash 查询
- [x] `geo_zone.py` — SELECT all enabled、INSERT、UPDATE
- [x] `event.py` — INSERT、SELECT by vehicle+time range
- [x] `location.py` — COPY batch insert（无普通 INSERT）
- [x] `work_session.py` — INSERT、UPDATE ended_at+duration
- [x] `command_log.py` — INSERT、UPDATE is_delivered

**Repository**（`app/db/repos/`）
- [x] `user_repo.py` — `find_by_username`、`verify_password`（bcrypt）、`create`
- [x] `vehicle_repo.py` — `find_active(fleet_id)`、`find_by_id`、`create`、`update`、`soft_delete`
- [x] `device_repo.py` — `find_by_imei`、`create`、`update_firmware`
- [x] `geo_zone_repo.py` — `find_all_enabled`、`create`、`update`、`delete`
- [x] `event_repo.py` — `insert`、`find_by_vehicle(fleet_id, time_range)`
- [x] `location_repo.py` — `insert_batch`（COPY 协议，参考 `ARCHITECTURE.md §7.4`）
- [x] `work_session_repo.py` — `open_session`、`close_session`
- [x] `command_log_repo.py` — `insert`、`mark_delivered`

**Cache**
- [x] `app/cache/session_repo.py` — `get`、`set`、`delete`（Redis JSON）

### 验收标准

```bash
pytest tests/repos/ -v    # 所有 Repo 测试通过（testcontainers 真实 DB）
```

---

## 阶段 3：认证与权限 ✅

**目标**：登录/登出可用，所有后续 HTTP 接口均可接入权限守卫。

### 任务清单

- [x] `app/models/domain.py` — `SessionData` dataclass（参考 `ARCHITECTURE.md §9.1`）
- [x] `app/models/http_user.py` — `LoginRequest` / `LoginResponse`
- [x] `app/services/auth_service.py` — `login`（bcrypt 验证 + session 写入）、`logout`
- [x] `app/http/deps.py` — `require_auth`、`require_manager`、`require_password_confirm`（参考 `ARCHITECTURE.md §9.2`）
- [x] `app/http/app.py` — `create_app()` 工厂，注册路由与异常处理器
- [x] `app/http/routers/router_auth.py` — `POST /api/auth/login`、`POST /api/auth/logout`
- [x] `app/main.py` — TCP + HTTP 共存入口（参考 `TECHSTACK.md §1.3`）

### 验收标准

```bash
# ✅ 正确密码 → 200 + Set-Cookie
# ✅ 未登录访问受保护接口 → 403
# ✅ 带 Cookie 访问 /api/auth/me → 200 + 用户信息
```

---

## 阶段 4：HTTP 管理 API ✅

**目标**：后台所有 CRUD 接口可用，数据隔离（fleet_id 过滤）正确。

> 依赖阶段 2（Repo）+ 阶段 3（认证）。可与阶段 5 并行开发。

### 任务清单

**Pydantic 模型**（`app/models/`）
- [x] `http_vehicle.py` — `VehicleCreate` / `VehicleUpdate` / `VehicleResponse`
- [x] `http_geo_zone.py` — `GeoZoneCreate` / `GeoZoneUpdate` / `GeoZoneResponse`
- [x] `http_event.py` — `EventResponse`（只读）+ `DeviceCreate` / `BindRequest`
- [x] `http_user.py` — `UserCreate` / `UserResponse`（在 router_users 内联定义）

**Service**
- [x] `app/services/vehicle_service.py` — `list_vehicles(session)`、`create`、`update`、`delete`
- [x] `app/services/geo_zone_service.py` — CRUD

**Router**
- [x] `router_vehicles.py` — `GET /api/vehicles`、`POST`、`PUT /{id}`、`DELETE /{id}`
- [x] `router_devices.py` — `GET /api/devices`、设备绑定/解绑 `POST /api/devices/{id}/bind`
- [x] `router_geo_zones.py` — 围栏 CRUD（`GET/POST/PUT/DELETE /api/geo-zones`）
- [x] `router_events.py` — `GET /api/events`（支持 vehicle_id、time_range 过滤，分页）
- [x] `router_users.py` — `GET/POST/DELETE /api/users`（require_manager）
- [x] `router_admin.py` — `GET/POST/DELETE /api/admin/fleets`（车队管理）

### 验收标准

```bash
# ✅ 创建车队 POST /api/admin/fleets → 201
# ✅ 创建车辆 POST /api/vehicles → 200
# ✅ 创建围栏 POST /api/geo-zones → 200
# ✅ 查询事件 GET /api/events → {"total":0,"items":[]}
# ✅ Swagger 文档 /docs → 200
```

---

## 阶段 5：TCP 服务基础 ✅

**目标**：设备可接入，注册、心跳、时间/天气响应正常，定位点写入 DB。

> 依赖阶段 2（Repo）+ 阶段 3（Config/main.py）。可与阶段 4 并行开发。

### 任务清单

**Protocol 层**
- [x] `app/models/tcp_packets.py` — `RegisterPacket` / `GpsPacket` / `FullStatePacket`
- [x] `app/tcp/protocol.py` — 换行符分帧、JSON 解析、字段归一化、IMEI 提取

**Core**
- [x] `app/core/device_registry.py` — `DeviceState` + `DeviceRegistry`（参考 `ARCHITECTURE.md §2.1`）
- [x] `app/core/event_bus.py` — `EventBus` pub/sub（参考 `ARCHITECTURE.md §2.2`）

**TCP Entry**
- [x] `app/tcp/server.py` — `asyncio.start_server` + 心跳监控后台任务
- [x] `app/tcp/connection.py` — 单连接生命周期：读取循环、异常捕获、注册/注销
- [x] `app/tcp/handlers/register_handler.py` — 设备注册 + 欢迎语下发（`gm`/`ga`/`gn`）
- [x] `app/tcp/handlers/heartbeat_handler.py` — 更新内存时间戳 + Redis TTL
- [x] `app/tcp/handlers/time_weather_handler.py` — 响应 `rt` / `rw` 请求

**Cache / Service**
- [x] `app/cache/weather_cache.py` — Redis 缓存天气，TTL 30 min
- [x] `app/cache/heartbeat_cache.py` — Redis `hb:{device_id}` TTL 90s
- [x] `app/services/weather_service.py` — httpx 请求 wttr.in，解析温度+天气码

### 验收标准

```bash
# ✅ tcp_server_started port=8901
# ✅ 发送注册包 → device_auto_created + device_registered + greeting_sent(gn)
# ✅ 断线 → device_unregistered + tcp_disconnected
```

---

## 阶段 6：业务逻辑核心 ✅

**目标**：GPS 数据流完整处理：超速 → 指令下发 → 事件写入；围栏进出、作业状态机、轨迹分段正常运行。

> 依赖阶段 4（geo_zone 数据可用）+ 阶段 5（TCP 连接基础）。

### 任务清单

**坐标转换与围栏**
- [x] `app/services/geofence_service.py` — WGS-84 → GCJ-02 转换函数、点在多边形（射线法）、加载活跃围栏列表（从 DB 或内存缓存）

**告警逻辑**
- [x] `app/cache/debounce.py` — `try_fire_alert(redis, device_id, alert_type, cooldown_s)` → Redis SETNX
- [x] `app/services/alert_service.py` — `process_location(state, packet)` → 检查超速（区域优先/全局兜底）+ 越界 + 禁运时段，返回 `Command | None`

**作业状态机**
- [x] `app/services/work_state_service.py` — 状态机：`loading` / `unloading` / `transport_loaded` / `transport_empty` / `unknown`；驻留时长判定；`work_session` 开关

**轨迹分段**
- [x] `app/services/track_segment_service.py` — 停车/掉线超阈值（默认 10 min）切段逻辑；`track_segment` 开关写入

**指令下发**
- [x] `app/services/command_service.py` — `send(device_id, cmd)` → `DeviceRegistry.send_command` + `command_log` 写入

**GPS Handler 总装**
- [x] `app/tcp/handlers/gps_handler.py` — 完整流程（参考 `ARCHITECTURE.md §3.1` 时序图）：
  1. `DeviceRegistry.push_point`
  2. `LocationRepo.insert_batch`
  3. `AlertService.process_location` → 如有命令则下发
  4. `WorkStateService.update`
  5. `TrackSegmentService.update`
  6. `EventBus.publish("location:{fleet_id}", frame)`
- [x] `app/tcp/handlers/full_state_handler.py` — 处理低频全量包（更新 ICCID、固件、LBS 位置、电压等）

### 验收标准

```bash
pytest tests/services/test_alert_service.py -v
pytest tests/services/test_work_state_service.py -v
pytest tests/tcp/test_gps_handler.py -v
# 场景：发送速度=95 的 GPS 包（全局限速 80）→ event 表写入 overspeed，command_log 写入 ws
# 场景：发送速度=95 的 GPS 包（区域限速 100）→ 不触发超速
# 场景：10 秒内第二次超速 → 防抖，不重复下发
# 场景：车辆进入装料区驻留 6 分钟 → work_session.state=loading
```

---

## 阶段 7：实时推送（SSE）✅

**目标**：前端可通过 SSE 接收实时定位帧与告警事件。

### 任务清单

- [x] `app/core/event_bus.py` — `EventBus`（参考 `ARCHITECTURE.md §2.2`）；订阅者队列 `maxsize=200`，超出丢弃最旧
- [x] `app/http/routers/router_stream.py` — SSE 接口：
  - `GET /api/stream/locations` — 订阅 `location:{fleet_id}` 或 `location:all`
  - `GET /api/stream/alerts` — 订阅 `alert:{fleet_id}` 或 `alert:all`
- [x] `app/http/routers/router_tcp_messages.py` — 调试接口：TCP 原始收发消息环形缓冲查询

### 验收标准

```bash
# ✅ curl -N --cookie "tmss_session=xxx" http://localhost:8900/api/stream/locations
# 预期：设备发送 GPS 包后，SSE 流实时收到 data: {...}
```

---

## 阶段 8：后台任务 ✅（手动）

**目标**：设备离线自动检测；月度分区自动创建，无需手工 DDL。

### 任务清单

- [x] `app/tasks/heartbeat_scanner.py` — 每 10 秒扫描 `DeviceRegistry`，对 90 秒未心跳设备：
  1. 调用 `DeviceRegistry.unregister`
  2. 写入 `event(event_type='device_offline')`
  3. `EventBus.publish("device_state", {...})`
- [x] `app/tasks/partition_creator.py` — 每月 25 日 00:00 为下个月创建 `location_point` 分区
- [x] 在 `app/main.py` 中通过 `task_registry.spawn` 启动以上两个任务

### 验收标准

```bash
# 场景：设备连接后 90 秒不发心跳 → event 表新增 device_offline 记录
# 场景：当月 25 日后查看 pg，下月分区已存在
```

---

## 阶段 9：前端基础 ✅

**目标**：管理后台可用（登录、车辆/设备/围栏管理、事件查询）。

### 任务清单

- [x] `frontend/` Vue 3 + Vite + TypeScript + Element Plus 骨架
- [x] `vue-router` 路由：登录页 / 仪表盘 / 车辆管理 / 设备管理 / 围栏管理 / 事件查询 / 用户管理 / 轨迹查询
- [x] `pinia` stores：`useAuthStore`（session）、`useTabsStore`
- [x] `axios` 封装：统一 `{ ok, data/code/message }` 响应解析
- [x] 权限路由守卫：未登录跳转 `/login`；`fleet_captain` 隐藏系统设置
- [x] 登录页面（浅蓝科技主题，水滴图标，系统名称：姚家平水利枢纽土方运输智能管控系统）
- [x] 车辆管理页（列表 + 新增/编辑/删除 + 绑定设备 + 家用车型不填载重）
- [x] 围栏管理页（高德地图绘制多边形 + 列表）
- [x] 事件查询页（时间范围过滤 + 分页）
- [x] 设备管理页（管理员可删除设备 + 同步注销内存注册）
- [x] 用户管理、车队管理、系统设置页
- [x] `TabBar` 多标签页组件（keep-alive 保留状态）

### 验收标准

```bash
# ✅ manager 登录后可见全部车辆；fleet_captain 登录后只见本车队车辆
# ✅ 新增车辆 → 列表出现；删除车辆 → 列表消失
# ✅ 多标签页切换，每个页面状态独立保留
```

---

## 阶段 10：大屏 ✅

**目标**：实时大屏可用（车辆地图 + 状态统计 + 告警列表）。

### 任务清单

- [x] 大屏路由 `/dashboard`
- [x] 高德地图初始化 + `AMap.Marker` 车辆图标（按作业状态颜色区分）
- [x] SSE 接入（`useSSE` composable）→ 实时更新 `AMap.Marker` 位置
- [x] 围栏 `AMap.Polygon` 叠加层
- [x] 告警弹窗（收到 `alert:*` 事件时触发）
- [x] 在线车辆列表、今日告警列表侧边栏
- [x] manager 看全部车辆，fleet_captain 看本车队车辆（前端自动过滤）

### 验收标准

```bash
# ✅ 设备发送 GPS 包 → 地图上车辆图标位置实时移动
# ✅ 超速 → 页面出现告警弹窗
```

---

## 阶段 11：历史轨迹查询 ✅

**目标**：管理后台可查询、回放历史轨迹，管理员可删除异常轨迹段。

### 任务清单

**后端**
- [x] `app/db/repos/track_query_repo.py` — `TrackQueryRepo`：
  - `list_segments` — 按车辆/时间范围分页查询轨迹段，从起止定位点取 `loc_type` 用于坐标系判断
  - `get_points` — 获取段内定位点（最多 25 000 点，TABLESAMPLE 降采样）
  - `delete_segment` — 管理员硬删除轨迹段及其定位点（事务）
- [x] `app/http/routers/router_track_segments.py` — 轨迹段 API：
  - `GET /api/track-segments` — 查询轨迹段列表（`require_auth`）
  - `GET /api/track-segments/{id}/points` — 获取定位点（`require_auth`）
  - `DELETE /api/track-segments/{id}` — 删除轨迹段（`require_manager`）
  - WGS-84 → GCJ-02 坐标转换（GPS 定位点经 `wgs84_to_gcj02` 转换后返回，LBS 直接使用）

**前端**
- [x] `frontend/src/api/tracks.ts` — 轨迹 API 客户端（list / points / delete）
- [x] `frontend/src/views/TracksView.vue` — 历史轨迹查询与回放：
  - 时间 + 车牌过滤，轨迹段列表
  - 点击行加载定位点，AMap.Polyline 绘制 + AMap.Marker 起止点
  - 回放控制（播放/暂停/速度/时间轴滑块）
  - 渐进式逆地理编码（`requestIdleCallback` 后台补全地址，不阻塞 UI）
  - 选中行 300ms 过渡动画（`trackStageRevealed` + opacity transition）
  - 管理员显示"删除"按钮，确认后软删除并从列表移除
  - 性能优化：`shallowRef`、折线简化（MAX_POLYLINE_VERTICES=480）、`setFitView(immediately=true)`

### 验收标准

```bash
# ✅ 选择时间范围 → 轨迹列表加载
# ✅ 点击轨迹行 → 地图绘制折线 + 起止点 Marker + 300ms 过渡动画
# ✅ 管理员点击删除 → 确认弹窗 → 删除成功 → 从列表移除
# ✅ 折线与路网对齐（GCJ-02 坐标）
```

---

## 阶段 12：系统完善 ✅

**目标**：功能细节打磨、稳定性修复、UI 优化。

### 任务清单

**车辆管理**
- [x] 新增车型"家用车"（`passenger_car`）：选择此车型时自动清除载重字段，后端 Pydantic validator + SQL CASE 双重保障
- [x] 修复 `ElInputNumber` 收到字符串型 `load_capacity`（后端 Decimal → JSON string）导致 prop 类型警告：前端 `normalizeVehicle` 函数转换
- [x] 车辆新增/编辑支持驾驶员姓名字段（`driver_name`，V002 迁移）

**TCP 协议解析**
- [x] `FullStatePacket` 新增 `AliasChoices` 支持设备短字段名映射（`ic→iccid`、`q→signal_strength`、`vb→battery_voltage`、`dt→report_time`）
- [x] ICCID 自动补全：首次收到含 `ic` 字段的全量包时自动写入 DB（`PATCH_ICCID_IF_EMPTY_SQL` 幂等更新，不覆盖已有值）

**设备管理**
- [x] 管理员可删除设备：HTTP DELETE 同时触发内存 `DeviceRegistry` 注销（unbind + unregister）

**前端 UI**
- [x] 登录页全面重设计：浅蓝科技渐变背景（网格底纹 + 浮动光晕）、磨砂玻璃卡片、水滴主题图标
- [x] 系统名称更改为"姚家平水利枢纽土方运输智能管控系统"（英文副标题 Truck Monitoring System Simplify 保持不变）
- [x] 修复 Element Plus MessageBox 弹出时底图偏移：`scrollbar-gutter: stable` 全局样式 + `lockScroll: false`

### 验收标准

```bash
# ✅ 选择家用车型 → 载重输入框隐藏 → 保存后 load_capacity=NULL
# ✅ 设备发送含 ic 字段全量包 → DB iccid 字段自动补全
# ✅ 管理员删除设备 → DB 软删除 + 内存注销
# ✅ 打开删除确认弹窗 → 背景地图无偏移
```

---

## 开放性决策点

以下问题在开发前需要团队确认，避免返工：

| # | 问题 | 影响范围 | 当前默认 |
|---|---|---|---|
| 1 | **围栏是全局共享还是车队私有？** | `geo_zone` 表是否加 `fleet_id` | 当前：全局共享（无 fleet_id） |
| 2 | **急弯会车是否双向提醒？** | `alert_service` 会车逻辑复杂度 | `详细说明.md §急弯会车` 标注「待明确」 |
| 3 | **越界判定：不在任意限行围栏内 = 越界** | `geofence_service` 判定逻辑 | `详细说明.md` 当前逻辑如此，建议二次确认 |
| 4 | **`alembic` 迁移文件命名** | `alembic revision` 生成后需手动重命名 | 命名规范：`V{NNN}__{description}.py` |
| 5 | **多进程部署时 `DeviceRegistry` 迁移策略** | 当前进程内单例，水平扩展需迁至 Redis | 开发阶段单进程，上线后评估 |
| 6 | **`operation_ban` 跨零点逻辑** | `alert_service` 时段判定 | 需封装统一函数，`DATABASE.md §待补充` 已记录 |

---

## 附录：各阶段交付物速查

| 阶段 | 核心文件 | 可验证产物 |
|---|---|---|
| 1 地基 | `config.py` `core/` `alembic/` | `alembic upgrade head` 无报错 |
| 2 数据访问层 | `db/repos/` `db/queries/` `cache/` | `pytest tests/repos/` 全绿 |
| 3 认证 | `services/auth_service.py` `http/deps.py` `router_auth.py` | 登录/登出集成测试 |
| 4 HTTP API | `models/http_*.py` `services/*_service.py` `http/routers/` | `pytest tests/http/` 全绿 |
| 5 TCP 基础 | `tcp/` `models/tcp_packets.py` `core/device_registry.py` | 设备接入 + 心跳集成测试 |
| 6 业务逻辑 | `services/alert_service.py` `geofence_service.py` 等 | `pytest tests/services/` 全绿 |
| 7 SSE | `core/event_bus.py` `router_stream.py` | curl SSE 接收实时帧 ✅ |
| 8 后台任务 | `tasks/` | 90s 离线检测自动触发 ✅ |
| 9 前端 | `frontend/` | 管理后台可正常使用 ✅ |
| 10 大屏 | `frontend/views/DashboardView.vue` | 实时地图 + 告警弹窗 ✅ |
| 11 轨迹查询 | `router_track_segments.py` `track_query_repo.py` `TracksView.vue` | 轨迹回放 + 折线与路网对齐 ✅ |
| 12 系统完善 | `tcp_packets.py` `full_state_handler.py` `LoginView.vue` 等 | 家用车型/ICCID 补全/UI 重设计 ✅ |
