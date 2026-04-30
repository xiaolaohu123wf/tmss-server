# TMSS 技术栈选型

> **语言已确认：Python 3.12+**，配合完整的类型体系与 asyncio 纪律。  
> 本文档记录所有层的最终选型与理由，可直接用于指导工程骨架搭建。

---

## 技术层总览（已确认）

| 层 | 选型 | 关键包 |
| --- | --- | --- |
| 服务端语言 | **Python 3.12+** | 内置 asyncio |
| HTTP 框架 | **FastAPI 0.111+** | fastapi, uvicorn, uvloop |
| TCP 服务 | **asyncio 内置** | asyncio.start_server |
| 数据库驱动 | **asyncpg 0.29+** | asyncpg |
| 数据模型 / 校验 | **Pydantic v2** | pydantic |
| 数据库迁移 | **Alembic** | alembic |
| 缓存 / Session | **Redis 7** | redis[asyncio] |
| 代码质量 | **ruff + mypy** | ruff, mypy |
| 测试 | **pytest + pytest-asyncio** | pytest, pytest-asyncio, httpx |
| HTTP 客户端 | **httpx** | httpx（天气 API） |
| 日志 | **structlog** | structlog |
| 前端框架 | **Vue 3 + Vite** | vue, vite, element-plus |
| 地图组件 | **高德地图 JS API 2.0** | — |
| 可视化图表 | **ECharts 5** | echarts, vue-echarts |
| 实时推送 | **SSE（已定）** | FastAPI StreamingResponse |
| 部署 | **Docker Compose** | — |

---

## 一、服务端核心（Python 生态链）

### 1.1 语言规范：强制 type hints + mypy

选择 Python 但要获得接近静态语言的可维护性，需在整个项目强制以下规范：

```python
# ✅ 所有函数签名必须注明类型
async def save_location(
    conn: asyncpg.Connection,
    device_id: int,
    lat: float,
    lng: float,
    speed: float | None,
    recorded_at: datetime,
) -> int:
    ...

# ✅ 数据模型用 Pydantic v2（自动校验 + 序列化）
from pydantic import BaseModel, Field

class GpsPacket(BaseModel):
    device_id: str = Field(alias="deviceId")
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    speed: float | None = None
    altitude: float | None = None

# ✅ asyncio 任务必须处理异常
task = asyncio.create_task(some_coroutine())
task.add_done_callback(lambda t: t.exception() and logger.error("task failed", exc=t.exception()))
```

`mypy` 配置（`mypy.ini`）：
```ini
[mypy]
strict = true
plugins = pydantic.mypy
```

---

### 1.2 HTTP 框架：FastAPI

**选择理由**：
- 原生 async/await，与 asyncio TCP 服务共享同一事件循环
- Pydantic v2 直接集成，请求体自动校验，省去手写校验代码
- 自动生成 OpenAPI 文档（`/docs`），方便前端联调
- SSE 通过 `StreamingResponse` 开箱支持
- 依赖注入系统（`Depends`）非常适合数据库连接池注入、权限中间件

```python
from fastapi import FastAPI, Depends
from fastapi.responses import StreamingResponse

app = FastAPI(title="TMSS API", version="1.0.0")

# SSE 实时推送示例
@app.get("/api/stream/vehicles")
async def vehicle_stream(
    user: AppUser = Depends(require_fleet_captain_or_above)
):
    async def event_generator():
        async for frame in sse_bus.subscribe(fleet_id=user.fleet_id):
            yield f"data: {frame}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

**ASGI 服务器**：

| 环境 | 命令 |
| --- | --- |
| 开发 | `uvicorn app.main:app --reload --port 8900` |
| 生产（单进程） | `uvicorn app.main:app --workers 1 --loop uvloop` |
| 生产（多进程） | `gunicorn -k uvicorn.workers.UvicornWorker -w 2 app.main:app` |

> 注意：TCP 长连接服务（设备状态、300 点缓冲区）存在进程内存中，**多进程模式下状态不共享**；若要多进程，设备状态须迁移至 Redis。开发阶段单进程足够，上线后视负载再决定。

---

### 1.3 TCP 服务与 HTTP 共存模式

TCP 服务（端口 9000）与 HTTP 服务（端口 8080）跑在同一 asyncio 事件循环：

```python
# app/main.py
import asyncio
import uvicorn
from app.tcp.server import start_tcp_server
from app.http.app import create_app

async def main():
    # 启动 TCP 服务（非阻塞）
    tcp_server = await start_tcp_server(host="0.0.0.0", port=8901)

    # 启动 HTTP 服务
    http_app = create_app()
    config = uvicorn.Config(http_app, host="0.0.0.0", port=8900, loop="none")
    server = uvicorn.Server(config)
    await server.serve()  # 阻塞直到退出

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 二、数据库访问层

### 2.1 asyncpg — 异步 PostgreSQL 驱动 ✅

**选择理由**：
- Python 生态中性能最高的 PostgreSQL 驱动，比 psycopg3 快约 2–3 倍
- 完整支持 `JSONB`、数组类型、`COPY` 协议（批量写入）、`LISTEN/NOTIFY`
- 内置连接池 `asyncpg.Pool`，线程安全，适合 asyncio 场景
- 与 `TIMESTAMPTZ` 配合自动转换为 Python `datetime`（带时区）

```python
# app/db/pool.py
import asyncpg
from app.config import settings

_pool: asyncpg.Pool | None = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=5,
            max_size=20,
            command_timeout=30,
        )
    return _pool

# FastAPI 依赖注入
async def get_db(pool: asyncpg.Pool = Depends(get_pool)):
    async with pool.acquire() as conn:
        yield conn
```

**SQL 组织方式（推荐）**：手写 SQL 按模块分文件，配合 type hints：

```python
# app/db/queries/location.py
from datetime import datetime
import asyncpg

async def insert_location_batch(
    conn: asyncpg.Connection,
    rows: list[tuple[int, int | None, datetime, float, float, float | None, float | None, str]],
) -> None:
    """批量写入定位点，使用 COPY 协议，比逐行 INSERT 快 10x。"""
    await conn.copy_records_to_table(
        "location_point",
        records=rows,
        columns=["device_id", "vehicle_id", "recorded_at", "lat", "lng", "speed", "altitude", "loc_type"],
    )
```

**为什么不用 SQLAlchemy ORM**：

| 对比项 | asyncpg 裸 SQL | SQLAlchemy 2.0 async |
| --- | --- | --- |
| JSONB / 数组支持 | ✅ 原生 | ⚠ 需要自定义类型 |
| 分区表 COPY 写入 | ✅ 直接 | ⚠ 需要绕过 ORM |
| 查询可读性 | 高（SQL 即文档） | 中（ORM 表达式） |
| 学习成本 | 低 | 中 |
| 与 DATABASE.md 对应 | 完全一致 | 需要额外 Model 定义 |

---

### 2.2 Alembic — 数据库迁移

管理 `DATABASE.md` 中 DDL 的版本化演进：

```
alembic/
  versions/
    V001__init_schema.py    # 初始建表
    V002__add_fleet.py      # 新增 fleet 表
  env.py
  alembic.ini
```

```bash
# 生成新迁移
alembic revision --autogenerate -m "add_fleet_table"
# 执行迁移
alembic upgrade head
# 回滚一步
alembic downgrade -1
```

---

## 三、缓存与状态管理

### 3.1 Redis 7 + redis[asyncio]

**在本项目中的四个核心用途**：

| 用途 | Key 设计 | TTL |
| --- | --- | --- |
| Cookie Session | `session:{session_id}` | 24h（滑动续期） |
| 天气缓存 | `weather:{city}` | 30min |
| 设备最后心跳 | `hb:{device_id}` | 90s（心跳刷新）|
| 告警防抖 | `debounce:{device_id}:{alert_type}` | 10s |

```python
# app/cache/redis.py
from redis.asyncio import Redis, ConnectionPool
from app.config import settings

_pool: ConnectionPool | None = None

def get_redis() -> Redis:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return Redis(connection_pool=_pool)

# 告警防抖示例（SETNX = set if not exists）
async def try_fire_alert(redis: Redis, device_id: int, alert_type: str, cooldown_s: int) -> bool:
    key = f"debounce:{device_id}:{alert_type}"
    ok = await redis.set(key, "1", nx=True, ex=cooldown_s)
    return bool(ok)  # True=触发告警，False=冷却中
```

---

## 四、代码质量工具链

### 4.1 ruff — 一体化 Linter + Formatter

替代 black + flake8 + isort，速度快 10–100x：

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E", "F", "W",   # pycodestyle / pyflakes
    "I",             # isort
    "UP",            # pyupgrade
    "ANN",           # 类型注解
    "ASYNC",         # asyncio 反模式
    "B",             # bugbear
    "SIM",           # simplify
    "RET",           # return 优化
    "PL",            # pylint 子集
    "T20",           # 禁止 print
]
ignore = [
    "ANN101",        # 不强制 self 注解
    "ANN102",        # 不强制 cls 注解
    "PLR0913",       # 参数过多由 review 把关
]
```

```bash
ruff check .       # 检查
ruff format .      # 格式化
```

### 4.2 mypy — 静态类型检查

```bash
mypy app/ --strict
```

关键规则：
- `--strict` 模式：所有函数必须有类型注解，禁止 `Any`
- 配合 `pydantic.mypy` 插件：Pydantic model 字段类型自动推导
- CI 中作为门禁：mypy 不通过则不允许合并

### 4.3 pytest + pytest-asyncio — 测试

```python
# tests/test_tcp_handler.py
import pytest

@pytest.mark.asyncio
async def test_gps_packet_saved(db_conn, redis):
    packet = GpsPacket(device_id="123456789012345", lat=32.1, lng=118.9, speed=60.0)
    await handle_gps_packet(db_conn, redis, packet)
    row = await db_conn.fetchrow("SELECT * FROM location_point WHERE device_id = $1", 1)
    assert row["speed"] == 60.0
```

### 4.4 structlog — 结构化日志

```python
import structlog
logger = structlog.get_logger()

# 输出 JSON，便于后续日志聚合
await logger.ainfo("gps_received", device_id=device_id, lat=lat, lng=lng, speed=speed)
# {"event": "gps_received", "device_id": 42, "lat": 32.1, "lng": 118.9, "speed": 60.0, "timestamp": "..."}
```

---

## 五、前端

### 5.1 Vue 3 + Vite + Element Plus ✅

**选择理由**：
- Composition API + `<script setup>` 语法简洁，适合响应式实时数据更新
- Element Plus 提供完整后台管理组件（表格、表单、弹窗、权限按钮），开发效率高
- Vite 冷启动 < 1 秒，HMR 即时热更新
- 与 ECharts、高德地图的集成社区资料最丰富

**前端工具链**：

| 工具 | 用途 |
| --- | --- |
| `pinia` | 状态管理（替代 Vuex），轻量、类型友好 |
| `vue-router 4` | 路由（含权限守卫） |
| `axios` | HTTP 请求（拦截器统一处理 token/错误） |
| `@vueuse/core` | 组合式工具（`useEventSource` 直接处理 SSE） |
| `TypeScript` | 前端也强制类型，与后端 Pydantic 模型对齐 |
| `ESLint + Prettier` | 代码规范 |

**SSE 接入示例（@vueuse/core）**：
```typescript
import { useEventSource } from '@vueuse/core'

const { data } = useEventSource('/api/stream/vehicles', [], { withCredentials: true })

watch(data, (raw) => {
  const frame = JSON.parse(raw!)
  vehicleStore.updatePosition(frame)
})
```

---

## 六、地图与可视化

### 6.1 高德地图 JS API 2.0 ✅

**核心优势**：坐标系与数据库完全对齐（均为 GCJ-02），无需任何坐标转换。

主要使用场景：
- 实时车辆图标（`AMap.Marker` + `MoveAlong` 平滑动画）
- 围栏绘制与展示（`AMap.Polygon` 对应 `geo_zone.coordinates`）
- 历史轨迹回放（`AMap.Polyline` + 时间轴控件）
- 点击围栏查看详情（`overlay.on('click', ...)`)

申请步骤：高德开放平台 → 创建应用 → 获取 Web JS Key → 按量计费，每日免费额度 100 万次调用。

### 6.2 ECharts 5 + vue-echarts ✅

主要使用场景：
- 大屏状态仪表盘（在线车辆数、告警数、作业状态分布）
- 速度折线图（历史轨迹回放辅助面板）
- 作业统计柱状图（按车辆/时间段统计装卸次数）
- 事件趋势图（按天/周超速、越界趋势）

---

## 七、部署

### 7.1 Docker Compose

```yaml
# docker-compose.yml
services:
  app:
    build: .
    ports:
      - "8901:8901"   # TCP 设备接入
      - "8900:8900"   # HTTP API
    environment:
      - DATABASE_URL=postgresql://tmss:tmss@postgres:5432/tmss_db
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: tmss_db
      POSTGRES_USER: tmss
      POSTGRES_PASSWORD: tmss
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./alembic/sql:/docker-entrypoint-initdb.d  # 首次建库自动执行
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tmss"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes  # AOF 持久化

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./frontend/dist:/usr/share/nginx/html  # Vue 打包产物
    depends_on:
      - app

volumes:
  postgres_data:
  redis_data:
```

**Dockerfile（Python 多阶段构建）**：
```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install uv

FROM base AS deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM base AS runtime
COPY --from=deps /app/.venv /app/.venv
COPY app/ ./app/
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 9000 8080
CMD ["python", "-m", "app.main"]
```

> 使用 `uv`（Rust 实现的 pip 替代品）代替 pip，依赖安装速度快 10–100x。

---

## 八、完整依赖清单

```toml
# pyproject.toml
[project]
name = "tmss-server"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    # HTTP
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",   # [standard] 包含 uvloop + httptools
    "gunicorn>=22.0",

    # 数据库
    "asyncpg>=0.29",
    "alembic>=1.13",

    # 数据模型
    "pydantic[email]>=2.7",
    "pydantic-settings>=2.3",    # 配置管理（读取环境变量）

    # 缓存
    "redis[asyncio]>=5.0",

    # HTTP 客户端（天气 API）
    "httpx>=0.27",

    # 日志
    "structlog>=24.0",

    # 安全
    "bcrypt>=4.1",
]

[dependency-groups]
dev = [
    "mypy>=1.10",
    "ruff>=0.4",
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "httpx>=0.27",               # TestClient
    "testcontainers[postgres]>=4.0",  # 真实 PostgreSQL 容器测试
    "testcontainers[redis]>=4.0",     # 真实 Redis 容器测试
]
```

---

## 九、工程目录结构

> 此目录为唯一权威结构，与 `ARCHITECTURE.md §12` 完全一致。

```
tmss-server/
├── app/
│   ├── __init__.py
│   ├── main.py                       # 入口：启动 TCP + HTTP
│   ├── config.py                     # Settings（pydantic-settings）
│   │
│   ├── core/                         # 跨层基础设施（无业务）
│   │   ├── exceptions.py             # TmssError 异常层级
│   │   ├── task_registry.py          # 后台任务管理
│   │   ├── device_registry.py        # 在线设备状态（DeviceRegistry + DeviceState）
│   │   ├── event_bus.py              # 进程内 pub/sub
│   │   └── enums.py                  # WorkState / Command / UserRole
│   │
│   ├── models/                       # Pydantic 模型（Protocol 层）
│   │   ├── tcp_packets.py            # GpsPacket / RegisterPacket / FullStatePacket
│   │   ├── http_vehicle.py           # VehicleCreate / VehicleResponse
│   │   ├── http_geo_zone.py
│   │   ├── http_event.py
│   │   ├── http_user.py
│   │   └── domain.py                 # SessionData 等内部 DTO
│   │
│   ├── services/                     # Service 层（业务逻辑）
│   │   ├── alert_service.py          # 超速/越界判定 + 防抖
│   │   ├── geofence_service.py       # 点在多边形 + 坐标转换
│   │   ├── work_state_service.py     # 作业状态机
│   │   ├── command_service.py        # 指令下发
│   │   ├── track_segment_service.py  # 轨迹分段
│   │   ├── vehicle_service.py
│   │   ├── geo_zone_service.py
│   │   ├── auth_service.py
│   │   └── weather_service.py
│   │
│   ├── db/                           # Repository 层
│   │   ├── pool.py                   # asyncpg Pool 工厂
│   │   ├── deps.py                   # FastAPI get_db_conn
│   │   ├── repos/
│   │   │   ├── location_repo.py
│   │   │   ├── vehicle_repo.py
│   │   │   ├── device_repo.py
│   │   │   ├── geo_zone_repo.py
│   │   │   ├── event_repo.py
│   │   │   ├── work_session_repo.py
│   │   │   ├── command_log_repo.py
│   │   │   └── user_repo.py
│   │   └── queries/                  # SQL 字符串常量（禁止在 Repo 内联 SQL）
│   │       ├── location.py
│   │       ├── vehicle.py
│   │       ├── device.py
│   │       ├── geo_zone.py
│   │       ├── event.py
│   │       ├── work_session.py
│   │       ├── command_log.py
│   │       └── user.py
│   │
│   ├── cache/                        # Redis 封装
│   │   ├── pool.py                   # Redis 连接池
│   │   ├── session_repo.py           # Session CRUD
│   │   ├── weather_cache.py          # 天气缓存
│   │   ├── heartbeat_cache.py        # 心跳状态
│   │   └── debounce.py               # 告警防抖
│   │
│   ├── http/                         # HTTP Entry
│   │   ├── app.py                    # create_app() 工厂
│   │   ├── deps.py                   # require_auth / require_manager 等
│   │   ├── error_handler.py          # 全局异常处理
│   │   ├── response.py               # ok() 封装
│   │   └── routers/
│   │       ├── router_auth.py        # 登录 / 登出
│   │       ├── router_vehicles.py    # 车辆 CRUD
│   │       ├── router_devices.py     # 设备管理
│   │       ├── router_geo_zones.py   # 围栏配置
│   │       ├── router_events.py      # 事件查询
│   │       ├── router_users.py       # 用户管理
│   │       ├── router_admin.py       # 系统配置（需二次验证）
│   │       └── router_stream.py      # SSE 实时推送
│   │
│   ├── tcp/                          # TCP Entry
│   │   ├── server.py                 # asyncio.start_server
│   │   ├── connection.py             # 单个连接生命周期
│   │   ├── protocol.py               # 报文分帧 + 解析
│   │   └── handlers/
│   │       ├── register_handler.py   # 设备注册 + 欢迎语
│   │       ├── gps_handler.py        # 高频定位包处理
│   │       ├── full_state_handler.py # 低频全量状态包
│   │       ├── heartbeat_handler.py  # 心跳更新
│   │       └── time_weather_handler.py  # 时间/天气响应
│   │
│   └── tasks/                        # 周期性后台任务
│       ├── heartbeat_scanner.py      # 90 秒离线检测
│       └── partition_creator.py      # 月度分区自动创建
│
├── alembic/
│   ├── versions/
│   │   └── V001__init_schema.py      # 注意：alembic 生成后需手动重命名为 V{NNN}__ 格式
│   ├── env.py
│   └── alembic.ini
│
├── tests/
│   ├── conftest.py                   # testcontainers 数据库/Redis fixture
│   ├── services/
│   ├── repos/
│   ├── http/
│   └── tcp/
│
├── frontend/                         # Vue 3 + Vite 前端（独立子项目）
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── mypy.ini
├── .env.example
└── README.md
```

---

## 十、工作量估算

| 阶段 | 主要工作 | 估计耗时 |
| --- | --- | --- |
| 工程骨架 | 目录结构、依赖安装、Docker Compose、DB 迁移 | 0.5 天 |
| TCP 服务 | 设备注册、定位写入、心跳检测、指令下发 | 2–3 天 |
| 业务逻辑 | 超速/越界/围栏判定、作业状态机、防抖 | 3–4 天 |
| HTTP API | 车辆/设备/围栏 CRUD、事件查询、SSE 推送 | 3–5 天 |
| 认证权限 | Session 登录、角色中间件、数据隔离 | 1–2 天 |
| 前端基础 | Vue 骨架、路由、登录、后台管理页 | 2–3 天 |
| 大屏（待设计） | 高德地图 + 实时 SSE + ECharts 统计 | 3–5 天 |
