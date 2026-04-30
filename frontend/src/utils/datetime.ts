/**
 * 全站时间展示统一为中国（上海）时区。
 * 后端 API 一般为 ISO-8601 UTC。
 */
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

const CN_TZ = 'Asia/Shanghai'

function toChina(isoOrMs: string | number | null | undefined): dayjs.Dayjs | null {
  if (isoOrMs === null || isoOrMs === undefined || isoOrMs === '') return null
  const d = dayjs.utc(isoOrMs).tz(CN_TZ)
  return d.isValid() ? d : null
}

/** 完整日期时间，如 2026-04-30 14:29:13 */
export function formatChinaDateTime(
  isoOrMs: string | number | null | undefined,
  pattern = 'YYYY-MM-DD HH:mm:ss',
): string {
  const d = toChina(isoOrMs)
  return d ? d.format(pattern) : '—'
}

/** 两行：日期 + 时间（便于表格窄列） */
export function formatChinaDateTimeSplit(isoOrMs: string | number | null | undefined): {
  date: string
  time: string
} {
  const d = toChina(isoOrMs)
  if (!d) return { date: '—', time: '' }
  return { date: d.format('YYYY-MM-DD'), time: d.format('HH:mm:ss') }
}

export function chinaTimeZoneLabel(): string {
  return '中国时间'
}
