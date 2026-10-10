/**
 * Thin typed wrapper around the backend REST API.
 *
 * Requests use the backend origin configured with VITE_API_BASE_URL.
 */

import type {
  AnalyticsSummary,
  AuthResponse,
  ClickRecord,
  CreateURLPayload,
  Paginated,
  ShortURL,
  Timeline,
  TopURL,
  UpdateURLPayload,
  URLStats,
  User,
} from '../types'

const TOKEN_KEY = 'urlshortener.token'
const API_BASE_URL = parseApiBaseUrl(import.meta.env.VITE_API_BASE_URL)

function parseApiBaseUrl(value: string | undefined): URL {
  if (!value) {
    throw new Error('VITE_API_BASE_URL must be set to the backend origin.')
  }

  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new Error('VITE_API_BASE_URL must be an absolute URL, such as https://api.example.com.')
  }

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('VITE_API_BASE_URL must use HTTP or HTTPS.')
  }

  return url
}

export const tokenStore = {
  get: (): string | null => localStorage.getItem(TOKEN_KEY),
  set: (token: string): void => localStorage.setItem(TOKEN_KEY, token),
  clear: (): void => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  status: number
  /** FastAPI sends `detail` as either a string or a list of validation errors. */
  detail: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** Turn FastAPI's error body into something worth showing a user. */
function extractMessage(status: number, body: unknown): string {
  if (typeof body === 'string' && body) return body
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined
      if (first?.msg) {
        const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined
        return field ? `${field}: ${first.msg}` : first.msg
      }
    }
  }
  if (status === 401) return 'Your session has expired. Please log in again.'
  if (status === 404) return 'Not found.'
  if (status === 409) return 'That short code or alias is already taken.'
  if (status === 410) return 'This link has expired or been disabled.'
  return `Request failed (${status})`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = tokenStore.get()
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(new URL(path, API_BASE_URL), { ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Is the backend running?')
  }

  if (response.status === 401) {
    // Drop the dead token so the app falls back to the login screen.
    tokenStore.clear()
    throw new ApiError(401, 'Your session has expired. Please log in again.')
  }

  if (response.status === 204) return undefined as T

  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, extractMessage(response.status, body), body)
  }
  return body as T
}

const qs = (params: Record<string, string | number | boolean | undefined>): string => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '' && value !== null) search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

export const api = {
  // --- auth ---
  register: (email: string, password: string) =>
    request<AuthResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>('/api/auth/me'),

  // --- urls ---
  listURLs: (params: {
    page?: number
    limit?: number
    is_active?: boolean
    search?: string
    sort?: string
  } = {}) => request<Paginated<ShortURL>>(`/api/urls${qs(params)}`),

  getURL: (id: string) => request<ShortURL>(`/api/urls/${id}`),

  createURL: (payload: CreateURLPayload) =>
    request<ShortURL>('/api/urls', { method: 'POST', body: JSON.stringify(payload) }),

  updateURL: (id: string, payload: UpdateURLPayload) =>
    request<ShortURL>(`/api/urls/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  deleteURL: (id: string) => request<void>(`/api/urls/${id}`, { method: 'DELETE' }),

  stats: () => request<URLStats>('/api/urls/stats'),

  topURLs: (limit = 5) => request<TopURL[]>(`/api/urls/top${qs({ limit })}`),

  // --- analytics ---
  analytics: (id: string) => request<AnalyticsSummary>(`/api/urls/${id}/analytics`),

  timeline: (id: string, days = 30) =>
    request<Timeline>(`/api/urls/${id}/analytics/timeline${qs({ days })}`),

  clicks: (id: string, page = 1, limit = 20) =>
    request<Paginated<ClickRecord>>(`/api/urls/${id}/analytics/clicks${qs({ page, limit })}`),

  overviewTimeline: (days = 30) =>
    request<Timeline>(`/api/analytics/overview${qs({ days })}`),
}