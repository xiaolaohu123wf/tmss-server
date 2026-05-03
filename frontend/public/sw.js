// TMSS Service Worker
// 策略：应用外壳（HTML/JS/CSS）→ Cache First；API → Network First；地图瓦片 → Cache First
const CACHE_NAME = 'tmss-v1'
const AMAP_CACHE = 'tmss-amap-v1'

// 预缓存的应用外壳资源（构建时由 Vite 生成的入口）
const SHELL_URLS = ['/', '/manifest.webmanifest']

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting()),
  )
})

// ── Activate ──────────────────────────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== CACHE_NAME && k !== AMAP_CACHE)
            .map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // 1. API 请求（SSE / WebSocket / 登录等）→ 直接走网络，不缓存
  if (url.pathname.startsWith('/api/')) {
    return // 不拦截，交给浏览器
  }

  // 2. 高德地图瓦片 → Cache First（节省流量，地图在弱网下仍可用）
  if (url.hostname.includes('amap.com') || url.hostname.includes('gdimg.com')) {
    event.respondWith(
      caches.open(AMAP_CACHE).then((cache) =>
        cache.match(request).then((cached) => {
          if (cached) return cached
          return fetch(request).then((resp) => {
            if (resp.ok) cache.put(request, resp.clone())
            return resp
          })
        }),
      ),
    )
    return
  }

  // 3. 静态资源（JS / CSS / 图片）→ Cache First，回退到网络
  if (
    request.destination === 'script' ||
    request.destination === 'style' ||
    request.destination === 'image' ||
    request.destination === 'font'
  ) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(request).then((cached) => {
          if (cached) return cached
          return fetch(request).then((resp) => {
            if (resp.ok) cache.put(request, resp.clone())
            return resp
          })
        }),
      ),
    )
    return
  }

  // 4. 页面导航（HTML）→ Network First，离线时回退到缓存的 /
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/').then((r) => r || Response.error())),
    )
    return
  }
})
