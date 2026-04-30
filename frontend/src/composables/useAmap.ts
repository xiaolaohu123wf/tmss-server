import { ref, onUnmounted } from 'vue'

declare global {
  interface Window {
    AMap: typeof AMap
  }
}
declare const AMap: {
  Map: new (container: string | HTMLElement, options?: Record<string, unknown>) => AMapInstance
  Marker: new (options?: Record<string, unknown>) => AMapMarker
  Polygon: new (options?: Record<string, unknown>) => AMapPolygon
  Polyline: new (options?: Record<string, unknown>) => AMapPolyline
  MouseTool: new (map: AMapInstance) => AMapMouseTool
  LngLat: new (lng: number, lat: number) => unknown
  Icon: new (options?: Record<string, unknown>) => unknown
}

interface AMapInstance {
  add(overlay: unknown): void
  remove(overlay: unknown): void
  destroy(): void
  setCenter(position: [number, number]): void
  setZoom(zoom: number): void
  clearMap(): void
  setFitView(overlays?: unknown[]): void
}

export interface AMapMarker {
  setPosition(position: [number, number]): void
  getPosition(): { lng: number; lat: number } | null
  setMap(map: AMapInstance | null): void
  on(event: string, handler: () => void): void
  setLabel(label: { content: string; direction?: string }): void
  setExtData(data: unknown): void
  getExtData(): unknown
  setIcon(icon: unknown): void
}

export interface AMapPolygon {
  getPath(): Array<{ lng: number; lat: number }>
  setPath(path: [number, number][]): void
  setOptions(opts: Record<string, unknown>): void
  on(event: string, handler: () => void): void
  setExtData(data: unknown): void
  getExtData(): unknown
  setMap(map: AMapInstance | null): void
  show(): void
  hide(): void
}

interface AMapPolyline {
  setPath(path: [number, number][]): void
  setMap(map: AMapInstance | null): void
}

interface AMapMouseTool {
  polygon(options?: Record<string, unknown>): void
  /** clear=false keeps drawn shapes on map; clear=true removes them */
  close(clear: boolean): void
  on(event: string, handler: (e: { obj: AMapPolygon }) => void): void
}

export function useAmap(containerId: string, options?: Record<string, unknown>) {
  const map = ref<AMapInstance | null>(null)
  const isReady = ref(false)
  let activeTool: AMapMouseTool | null = null

  function init() {
    if (!window.AMap) {
      console.error('[useAmap] AMap script not loaded')
      return
    }
    map.value = new AMap.Map(containerId, {
      zoom: 13,
      center: [116.397428, 39.90923],
      mapStyle: 'amap://styles/normal',
      ...options,
    })
    isReady.value = true
  }

  function createMarker(position: [number, number], extData?: unknown, iconUrl?: string): AMapMarker {
    const opts: Record<string, unknown> = { position, map: map.value }
    if (iconUrl) opts.icon = new AMap.Icon({ image: iconUrl, size: [32, 32] as unknown as string })
    if (extData !== undefined) opts.extData = extData
    return new AMap.Marker(opts)
  }

  function createPolygon(
    path: [number, number][],
    extData?: unknown,
    color = '#1890ff',
    opacity = 0.15,
  ): AMapPolygon {
    return new AMap.Polygon({
      path,
      fillColor: color,
      fillOpacity: opacity,
      strokeColor: color,
      strokeWeight: 2,
      map: map.value,
      extData,
      cursor: 'pointer',
    })
  }

  function removePolygon(polygon: AMapPolygon) {
    polygon.setMap(null)
  }

  function updatePolygonColor(polygon: AMapPolygon, color: string) {
    polygon.setOptions({ fillColor: color, strokeColor: color })
  }

  function fitPolygon(polygon: AMapPolygon) {
    map.value?.setFitView([polygon as unknown])
  }

  /**
   * 启动多边形绘制。
   * 绘制完成后 callback 收到 (path, drawnPolygon)。
   * drawnPolygon 已留在地图上（close(false)），调用方决定是否保留或删除。
   * 调用方若需取消绘制，可调用返回的 cancelDraw()。
   */
  function startDrawPolygon(
    callback: (path: [number, number][], drawnPolygon: AMapPolygon) => void,
    drawColor = '#1890ff',
  ): { cancelDraw: () => void } {
    // 关闭上一次未完成的绘制
    activeTool?.close(true)

    const mouseTool = new AMap.MouseTool(map.value as AMapInstance)
    activeTool = mouseTool

    mouseTool.polygon({
      fillColor: drawColor,
      fillOpacity: 0.2,
      strokeColor: drawColor,
      strokeWeight: 2,
      strokeStyle: 'dashed',
    })

    mouseTool.on('draw', (e: { obj: AMapPolygon }) => {
      const polygon = e.obj
      const rawPath = polygon.getPath()
      const path: [number, number][] = rawPath.map((p) => [p.lng, p.lat])
      // close(false) = 关闭绘制工具，但保留刚画好的多边形
      mouseTool.close(false)
      activeTool = null
      callback(path, polygon)
    })

    return {
      cancelDraw: () => {
        // close(true) = 关闭并清除正在绘制的内容
        mouseTool.close(true)
        activeTool = null
      },
    }
  }

  onUnmounted(() => {
    activeTool?.close(true)
    map.value?.destroy()
    map.value = null
  })

  return {
    map,
    isReady,
    init,
    createMarker,
    createPolygon,
    removePolygon,
    updatePolygonColor,
    fitPolygon,
    startDrawPolygon,
  }
}
