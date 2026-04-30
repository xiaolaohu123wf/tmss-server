import { get } from './index'
import type { TmssEvent, EventQuery, PagedResult } from '@/types'

export const eventsApi = {
  list: (query: EventQuery = {}) =>
    get<PagedResult<TmssEvent>>('/events', { params: query }),
}
