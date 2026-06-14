# 高德地图在本项目中的使用说明（简版）

## 用途概要

| 层级 | 说明 |
|------|------|
| 前端 | 使用高德 **JS API 2.0**（`window.AMap`）绘制地图、车辆点、轨迹线、电子围栏及图层切换。 |
| 后端 | **不调用**高德 Web 服务 REST API；GPS 入库多为 WGS-84，推送与轨迹接口对外坐标为 **GCJ-02**，与高德底图一致。 |
| 数据 | `geo_zone.coordinates` 为前端高德绘制结果，坐标系 **GCJ-02**。 |

## 主要代码入口

| 文件 | 作用 |
|------|------|
| `frontend/index.html` | 安全配置 + 加载 JS API（Key、插件列表） |
| `frontend/src/composables/useAmap.ts` | 地图初始化、`Marker` / `Polyline` / `Polygon`、鼠标绘制围栏、`setLayers` |
| `frontend/src/views/DashboardView.vue` | 实时监控地图 |
| `frontend/src/views/GeoZonesView.vue` | 围栏绘制与管理 |
| `frontend/src/views/TracksView.vue` | 轨迹 + `AMap.Geocoder` 逆地理编码 |
| `frontend/src/components/screen/ScreenMap.vue` | 大屏地图（可选正射叠加） |
| `static/orthophoto_amap_test.html` | 正射影像 × 高德底图调试页 |

坐标转换逻辑：`app/services/geofence_service.py` 的 `wgs84_to_gcj02`，在轨迹路由、`gps_handler` 等中使用。

---

## 当前用到的密钥（以仓库内明文为准）

> **安全提示**：以下 Key 与安全密钥暴露在静态 HTML 中，任意访问前端的人均可在浏览器中看到。若为生产环境或对安全有要求，请在 [高德开放平台](https://console.amap.com/) 中为应用配置 **域名白名单 / 安全配置**，并尽快 **轮换密钥**；建议使用构建时注入或私有配置替换硬编码。

### 1. Web 端 Key（JavaScript Key）

用于加载脚本：

`https://webapi.amap.com/maps?v=2.0&key=<Key>&plugin=...`

| 取值 | 出现位置 |
|------|----------|
| `91974428fa4957121585bd2d90d842d4` | `frontend/index.html`、`static/orthophoto_amap_test.html` |

### 2. 安全密钥（Security JS Code）

与 JS API 2.0 配合使用，在脚本加载前设置：

```js
window._AMapSecurityConfig = { securityJsCode: '<安全密钥>' }
```

| 取值 | 出现位置 |
|------|----------|
| `cc48ce721d87c8f2222dcd65624a6005` | `frontend/index.html`、`static/orthophoto_amap_test.html` |

### 3. PWA / 离线缓存

`frontend/public/sw.js` 中对 `*.amap.com`、`*.gdimg.com` 的缓存不涉及上述密钥本身，仍为浏览器向高德请求的瓦片等资源。

---

## 参考文档

更完整的前端说明见 `docs/FRONTEND.md`、架构中的坐标约定见 `docs/ARCHITECTURE.md`。
