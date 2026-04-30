import { get } from './index'

export interface WeatherData {
  temp: string   // 温度字符串，如 "25" 或 "-3"
  code: number   // 天气码 0-7，与 OLED 显示一致
  name: string   // 中文名称：晴/多云/阴/小雨/大雨/雪/雾/雷暴
}

export async function getWeather(): Promise<WeatherData | null> {
  try {
    return await get<WeatherData | null>('/admin/weather')
  } catch {
    return null
  }
}
