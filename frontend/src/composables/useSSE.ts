import { ref, onUnmounted } from 'vue'

/**
 * Typed SSE composable.
 * - Automatically parses JSON payloads.
 * - Stops reconnecting on 4xx (e.g. 404 when backend Stage-7 is not yet deployed).
 * - Retries on transient network errors (max 10 times, 5s delay).
 */
export function useSSE<T = unknown>(url: string) {
  const lastMessage = ref<T | null>(null)
  const status = ref<'CONNECTING' | 'OPEN' | 'CLOSED' | 'ERROR'>('CONNECTING')
  const error = ref<string | null>(null)

  let es: EventSource | null = null
  let retries = 0
  const MAX_RETRIES = 10
  const RETRY_DELAY = 5000
  let retryTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    // Use fetch to pre-check the endpoint — avoids EventSource swallowing 404 silently
    fetch(url, { method: 'GET', credentials: 'include', headers: { Accept: 'text/event-stream' } })
      .then((res) => {
        if (res.status === 404 || res.status === 403 || res.status === 401) {
          // Permanent client error — don't reconnect
          status.value = 'ERROR'
          error.value = `SSE endpoint not available (HTTP ${res.status})`
          console.warn(`[useSSE] ${url} → ${res.status}, reconnect disabled`)
          return
        }
        // Endpoint exists — open real EventSource
        openEventSource()
      })
      .catch(() => {
        // Network error during preflight — may recover, schedule retry
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

    es.onmessage = (evt) => {
      if (!evt.data) return
      try {
        lastMessage.value = JSON.parse(evt.data) as T
      } catch {
        // ignore non-JSON keep-alive frames
      }
    }

    es.onerror = () => {
      status.value = 'ERROR'
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
    es?.close()
    es = null
    status.value = 'CLOSED'
  }

  // Start
  connect()

  onUnmounted(close)

  return { lastMessage, status, error, close }
}
