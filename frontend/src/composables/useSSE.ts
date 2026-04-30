import { ref, onUnmounted } from 'vue'

/**
 * Typed SSE composable.
 *
 * @param url       SSE 端点 URL
 * @param eventName 监听的命名事件（对应后端 `event: xxx\n` 字段）；
 *                  不传则监听无名 `message` 事件。
 *
 * 特性：
 * - 自动解析 JSON payload
 * - 4xx 响应停止重连（如 404）
 * - 网络错误最多重试 10 次，每次 5s 间隔
 */
export function useSSE<T = unknown>(url: string, eventName?: string) {
  const lastMessage = ref<T | null>(null)
  const status = ref<'CONNECTING' | 'OPEN' | 'CLOSED' | 'ERROR'>('CONNECTING')
  const error = ref<string | null>(null)

  let es: EventSource | null = null
  let retries = 0
  const MAX_RETRIES = 10
  const RETRY_DELAY = 5000
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  function handleData(evt: MessageEvent) {
    if (!evt.data) return
    try {
      lastMessage.value = JSON.parse(evt.data) as T
    } catch {
      // ignore non-JSON keep-alive frames
    }
  }

  function connect() {
    // 预检端点避免 EventSource 静默吞 404
    fetch(url, { method: 'GET', credentials: 'include', headers: { Accept: 'text/event-stream' } })
      .then((res) => {
        if (res.status === 404 || res.status === 403 || res.status === 401) {
          status.value = 'ERROR'
          error.value = `SSE endpoint not available (HTTP ${res.status})`
          console.warn(`[useSSE] ${url} → ${res.status}, reconnect disabled`)
          return
        }
        openEventSource()
      })
      .catch(() => {
        scheduleRetry()
      })
  }

  function openEventSource() {
    es = new EventSource(url, { withCredentials: true })
    status.value = 'CONNECTING'

    es.onopen = () => {
      status.value = 'OPEN'
      retries = 0
      error.value = null
    }

    if (eventName) {
      // 监听后端发出的命名事件（`event: location\n` 等）
      es.addEventListener(eventName, handleData)
    } else {
      // 监听无名 message 事件
      es.onmessage = handleData
    }

    es.onerror = () => {
      status.value = 'ERROR'
      if (eventName) es?.removeEventListener(eventName, handleData)
      es?.close()
      es = null
      scheduleRetry()
    }
  }

  function scheduleRetry() {
    if (retries >= MAX_RETRIES) {
      status.value = 'CLOSED'
      error.value = `SSE: exceeded ${MAX_RETRIES} retries`
      console.warn(`[useSSE] ${url} → max retries reached`)
      return
    }
    retries++
    retryTimer = setTimeout(connect, RETRY_DELAY)
  }

  function close() {
    if (retryTimer) clearTimeout(retryTimer)
    if (eventName) es?.removeEventListener(eventName, handleData)
    es?.close()
    es = null
    status.value = 'CLOSED'
  }

  connect()
  onUnmounted(close)

  return { lastMessage, status, error, close }
}
