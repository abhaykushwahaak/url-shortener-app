export interface User {
  id: string
  email: string
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface ShortURL {
  id: string
  original_url: string
  short_code: string
  custom_alias: string | null
  short_url: string
  is_active: boolean
  is_expired: boolean
  expires_at: string | null
  created_at: string
  updated_at: string
  total_clicks: number
  clicks_today: number
  clicks_this_week: number
}

export interface Paginated<T> {
  items: T[]
  page: number
  limit: number
  total: number
}

export interface URLStats {
  total_urls: number
  active_urls: number
  expired_urls: number
  total_clicks: number
}

export interface CountByKey {
  key: string
  count: number
}

export interface AnalyticsSummary {
  url_id: string
  short_code: string
  original_url: string
  total_clicks: number
  clicks_today: number
  clicks_this_week: number
  unique_visitors: number
  first_click_at: string | null
  last_click_at: string | null
  devices: CountByKey[]
  browsers: CountByKey[]
  referrers: CountByKey[]
  countries: CountByKey[]
}

export interface TimelinePoint {
  date: string
  clicks: number
}

export interface Timeline {
  url_id: string
  days: number
  points: TimelinePoint[]
}

export interface ClickRecord {
  id: number
  clicked_at: string | null
  device: string | null
  browser: string | null
  referrer: string | null
  ip_address: string | null
  country: string | null
}

export interface TopURL {
  url_id: string
  short_code: string
  original_url: string
  clicks: number
}

export interface CreateURLPayload {
  original_url: string
  custom_alias?: string | null
  expires_at?: string | null
}

export interface UpdateURLPayload {
  original_url?: string
  custom_alias?: string | null
  is_active?: boolean
  expires_at?: string | null
}