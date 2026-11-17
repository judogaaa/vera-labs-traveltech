import type { HotelTripContext, PlannedTrip, TripProgressStep } from '../types/trip'

const API_BASE = (import.meta.env.VITE_VISUAL_SEARCH_API_URL as string | undefined)?.replace(/\/$/, '') ||
  'http://127.0.0.1:8000'

export type TripApiError = {
  code: string
  message: string
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
let csrfPromise: Promise<string> | null = null

function readCsrf(data: unknown): string {
  if (data && typeof data === 'object' && typeof (data as { csrf?: unknown }).csrf === 'string') {
    return (data as { csrf: string }).csrf
  }
  throw { code: 'session_unavailable', message: 'Не удалось открыть сессию маршрутов' } satisfies TripApiError
}

async function csrfToken(): Promise<string> {
  if (!csrfPromise) {
    csrfPromise = fetch(`${API_BASE}/api/trips/session`, {
      credentials: 'include',
      signal: AbortSignal.timeout(8000),
    })
      .then(async (res) => {
        if (!res.ok) throw { code: 'session_unavailable', message: 'Не удалось открыть сессию маршрутов' } satisfies TripApiError
        return readCsrf(await res.json().catch(() => null))
      })
      .catch((err) => {
        csrfPromise = null
        throw err
      })
  }
  return csrfPromise
}

async function apiFetch(url: string, init: RequestInit, allowRetry = true): Promise<Response> {
  const method = (init.method || 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (!SAFE_METHODS.has(method)) {
    headers.set('X-CSRF-Token', await csrfToken())
  }
  const res = await fetch(url, { ...init, headers, credentials: 'include' })
  if (res.status === 403 && allowRetry && !SAFE_METHODS.has(method)) {
    const payload = await res.clone().json().catch(() => null)
    const detail = (payload as { detail?: { code?: string } } | null)?.detail
    if (detail?.code === 'csrf_failed') {
      // The cookie session rotated or expired: fetch a fresh token once.
      csrfPromise = null
      return apiFetch(url, init, false)
    }
  }
  return res
}

function parseError(data: unknown, fallback: string): TripApiError {
  if (data && typeof data === 'object') {
    const d = data as { detail?: { code?: string; message?: string } | string; code?: string; message?: string }
    if (d.detail && typeof d.detail === 'object') {
      return { code: d.detail.code || 'error', message: d.detail.message || fallback }
    }
    if (typeof d.detail === 'string') return { code: 'error', message: d.detail }
    if (d.message) return { code: d.code || 'error', message: d.message }
  }
  return { code: 'error', message: fallback }
}

export async function fetchTripStatus(): Promise<Record<string, unknown>> {
  let res: Response
  try {
    res = await apiFetch(`${API_BASE}/api/trips/status`, { signal: AbortSignal.timeout(8000) })
  } catch {
    throw {
      code: 'network_unavailable',
      message: 'Сервер маршрутов недоступен. Проверьте, что backend запущен на :8000.',
    } satisfies TripApiError
  }
  if (!res.ok) throw parseError(await res.json().catch(() => null), 'Status unavailable')
  return res.json()
}

export async function planTrip(message: string, hotel?: HotelTripContext | null, tripId?: string | null): Promise<PlannedTrip> {
  let res: Response
  try {
    res = await apiFetch(`${API_BASE}/api/trips/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, hotel: hotel ?? null, tripId: tripId ?? null }),
      signal: AbortSignal.timeout(120000),
    })
  } catch {
    throw {
      code: 'network_unavailable',
      message: 'Сервер маршрутов недоступен. Проверьте, что backend запущен.',
    } satisfies TripApiError
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) throw parseError(data, 'Не удалось построить маршрут')
  return data.trip as PlannedTrip
}

export async function chatTrip(tripId: string, message: string): Promise<PlannedTrip> {
  let res: Response
  try {
    res = await apiFetch(`${API_BASE}/api/trips/${tripId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
      signal: AbortSignal.timeout(120000),
    })
  } catch {
    throw {
      code: 'network_unavailable',
      message: 'Сервер маршрутов недоступен. Проверьте, что backend запущен.',
    } satisfies TripApiError
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) throw parseError(data, 'Не удалось изменить маршрут')
  return data.trip as PlannedTrip
}

export async function getTrip(tripId: string): Promise<PlannedTrip> {
  let res: Response
  try {
    res = await apiFetch(`${API_BASE}/api/trips/${tripId}`, { signal: AbortSignal.timeout(15000) })
  } catch {
    throw {
      code: 'network_unavailable',
      message: 'Сервер маршрутов недоступен. Проверьте, что backend запущен.',
    } satisfies TripApiError
  }
  const data = await res.json().catch(() => null)
  if (!res.ok) throw parseError(data, 'Поездка не найдена')
  return data.trip as PlannedTrip
}

export function tripPdfUrl(tripId: string): string {
  const link = encodeURIComponent(`${window.location.origin}/oh-route?trip=${tripId}`)
  return `${API_BASE}/api/trips/${tripId}/pdf?link=${link}`
}

export async function planTripWithProgress(
  message: string,
  hotel: HotelTripContext | null | undefined,
  onProgress: (step: TripProgressStep) => void,
  tripId?: string | null,
): Promise<PlannedTrip> {
  const body = JSON.stringify({ message, hotel: hotel ?? null, tripId: tripId ?? null })
  let res: Response

  try {
    res = await apiFetch(`${API_BASE}/api/trips/plan/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body,
      signal: AbortSignal.timeout(180000),
    })
  } catch {
    throw {
      code: 'network_unavailable',
      message: 'Сервер маршрутов недоступен. Проверьте, что backend запущен.',
    } satisfies TripApiError
  }

  // Only a genuinely missing streaming endpoint may use the non-streaming API.
  // Retrying on SSE error events, timeouts or broken connections duplicates plans.
  if ([404, 405, 501].includes(res.status)) {
    return planTrip(message, hotel, tripId)
  }
  if (!res.ok) {
    throw parseError(await res.json().catch(() => null), 'Не удалось построить маршрут')
  }
  if (!res.body) {
    throw { code: 'stream_unavailable', message: 'Сервер не вернул поток маршрута' } satisfies TripApiError
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let trip: PlannedTrip | null = null

  const consume = (chunk: string) => {
    for (const line of chunk.split('\n')) {
      if (!line.startsWith('data: ')) continue
      const payload = JSON.parse(line.slice(6)) as {
        type: string
        step?: string
        trip?: PlannedTrip
        code?: string
        message?: string
      }
      if (payload.type === 'progress' && payload.step) onProgress(payload.step)
      if (payload.type === 'done' && payload.trip) trip = payload.trip
      if (payload.type === 'error') {
        throw {
          code: payload.code || 'plan_failed',
          message: payload.message || 'Не удалось построить маршрут',
        } satisfies TripApiError
      }
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''
      for (const chunk of chunks) consume(chunk)
    }
    buffer += decoder.decode().replace(/\r\n/g, '\n')
    if (buffer.trim()) consume(buffer)
  } finally {
    reader.releaseLock()
  }

  if (trip) return trip
  throw {
    code: 'stream_interrupted',
    message: 'Построение маршрута прервалось. Попробуйте ещё раз.',
  } satisfies TripApiError
}

export { API_BASE as TRIP_API_BASE }
