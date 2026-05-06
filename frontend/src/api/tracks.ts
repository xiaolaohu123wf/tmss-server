import { get, del } from './index'

export type SegmentType =
  | 'loading'
  | 'unloading'
  | 'transport_loaded'
  | 'transport_empty'
  | 'unknown'
  | 'idle'
  | null

/** 列表项内 start_/end_ lat/lng 为 GCJ-02（高德地图） */
export interface TrackSegment {
  id: number
  vehicle_id: number | null
  license_plate: string | null
  started_at: string
  ended_at: string | null
  distance_km: number
  segment_type: SegmentType
  start_zone_name: string | null
  end_zone_name: string | null
  cargo_name: string | null
  start_lat: number | null
  start_lng: number | null
  end_lat: number | null
  end_lng: number | null
  /** 运输段查询 points 时应附带的缓冲分钟数（后端注入，前端直接透传） */
  buffer_min: number
}

/** 轨迹点 lat/lng 为 GCJ-02（高德地图） */
export interface TrackPoint {
  recorded_at: string
  lat: number
  lng: number
  speed: number | null
  loc_type: string
}

function q(u: string, p: Record<string, string | number | boolean | undefined>) {
  const s = new URLSearchParams()
  for (const [k, v] of Object.entries(p)) {
    if (v === undefined) continue
    s.set(k, String(v))
  }
  const qs = s.toString()
  return qs ? `${u}?${qs}` : u
}

export const tracksApi = {
  list: (params: {
    from: string
    to: string
    vehicle_id?: number
    limit?: number
    min_distance_km?: number
    show_idle?: boolean
  }) =>
    get<TrackSegment[]>(
      q('/track-segments', {
        from: params.from,
        to: params.to,
        vehicle_id: params.vehicle_id,
        limit: params.limit,
        min_distance_km: params.min_distance_km,
        show_idle: params.show_idle,
      }),
    ),

  points: (segmentId: number, limit?: number, bufferMin?: number) =>
    get<TrackPoint[]>(
      q(`/track-segments/${segmentId}/points`, {
        limit,
        buffer_min: bufferMin,
      }),
    ),

  /** 管理员：删除轨迹段 */
  delete: (segmentId: number) => del<null>(`/track-segments/${segmentId}`),
}
