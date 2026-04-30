import { get, del } from './index'

/** 列表项内 start_/end_ lat/lng 为 GCJ-02（高德地图） */
export interface TrackSegment {
  id: number
  vehicle_id: number | null
  license_plate: string | null
  started_at: string
  ended_at: string | null
  distance_km: number
  start_zone_name: string | null
  end_zone_name: string | null
  cargo_name: string | null
  start_lat: number | null
  start_lng: number | null
  end_lat: number | null
  end_lng: number | null
}

/** 轨迹点 lat/lng 为 GCJ-02（高德地图） */
export interface TrackPoint {
  recorded_at: string
  lat: number
  lng: number
  speed: number | null
  loc_type: string
}

function q(u: string, p: Record<string, string | number | undefined>) {
  const s = new URLSearchParams()
  for (const [k, v] of Object.entries(p)) {
    if (v === undefined) continue
    s.set(k, String(v))
  }
  const qs = s.toString()
  return qs ? `${u}?${qs}` : u
}

export const tracksApi = {
  list: (params: { from: string; to: string; vehicle_id?: number; limit?: number }) =>
    get<TrackSegment[]>(
      q('/track-segments', {
        from: params.from,
        to: params.to,
        vehicle_id: params.vehicle_id,
        limit: params.limit,
      }),
    ),

  points: (segmentId: number, limit?: number) =>
    get<TrackPoint[]>(
      q(`/track-segments/${segmentId}/points`, { limit }),
    ),

  /** 管理员：删除轨迹段及下属定位点 */
  delete: (segmentId: number) => del<null>(`/track-segments/${segmentId}`),
}
