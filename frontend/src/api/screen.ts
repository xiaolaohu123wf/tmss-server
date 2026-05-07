import { get } from './index'

export interface ScreenSummary {
  vehicle_count: number
  fleet_count: number
  user_count: number
  online_count: number
}

export interface TypeStat {
  total_km: number
  total_min: number
  count: number
}

export interface DailyCount {
  day: string
  count: number
}

export interface SegmentStats {
  mileage_by_type: Record<string, TypeStat>
  daily_trips: DailyCount[]
}

export interface AlarmStats {
  total: number
  overspeed: number
  blind_zone: number
  out_of_bounds: number
  daily: DailyCount[]
}

export interface EfficiencyStats {
  utilization_rate: number
  loaded_ratio: number
  avg_transport_min: number
  total_trips: number
  transport_trips: number
  type_stats: Record<string, { count: number; avg_min: number }>
}

export const screenApi = {
  summary: () => get<ScreenSummary>('/screen/summary'),
  segmentStats: () => get<SegmentStats>('/screen/segment-stats'),
  alarmStats: () => get<AlarmStats>('/screen/alarm-stats'),
  efficiency: () => get<EfficiencyStats>('/screen/efficiency'),
}
