/**
 * Typed client for /api/hotel-intelligence/*.
 * Reuses the same VITE_VISUAL_SEARCH_API_URL base as trip planner / visual search.
 *
 * Security: NEVER embed HOTEL_INTELLIGENCE_WRITE_TOKEN in the frontend.
 * Local demo writes use POST /demo/session → HttpOnly cookie (loopback only).
 */
import type {
  AttributeDefinition,
  AttributeObservation,
  ConflictRecord,
  EnrichResponse,
  HotelIntelligenceApiError,
  HotelierQuestion,
  IntelligenceHotel,
  IntelligenceStatus,
  SearchResponse,
} from './types'

export const HI_API_BASE =
  (import.meta.env.VITE_VISUAL_SEARCH_API_URL as string | undefined)?.replace(/\/$/, '') ||
  'http://127.0.0.1:8000'

/** Marks hotelier answers as simulated; does NOT authorize writes by itself. */
export const HI_DEMO_MUTATION_HEADER: Record<string, string> = {
  'X-Demo-Mutation': '1',
}

const DEFAULT_TIMEOUT_MS = 20_000
const SEARCH_TIMEOUT_MS = 45_000
const ENRICH_TIMEOUT_MS = 120_000

let demoSessionPromise: Promise<boolean> | null = null

/** Obtain HttpOnly demo write cookie from the API (loopback + DEMO_MODE). */
export async function ensureDemoSession(signal?: AbortSignal): Promise<boolean> {
  if (!demoSessionPromise) {
    demoSessionPromise = (async () => {
      try {
        const res = await fetch(`${HI_API_BASE}/api/hotel-intelligence/demo/session`, {
          method: 'POST',
          credentials: 'include',
          signal,
        })
        return res.ok
      } catch {
        return false
      } finally {
        // Allow retry on next write if this failed
      }
    })()
  }
  const ok = await demoSessionPromise
  if (!ok) demoSessionPromise = null
  return ok
}

export function parseHotelIntelligenceError(
  data: unknown,
  fallback: string,
): HotelIntelligenceApiError {
  if (data && typeof data === 'object') {
    const d = data as {
      detail?: { code?: string; message?: string } | string
      code?: string
      message?: string
    }
    if (d.detail && typeof d.detail === 'object') {
      return {
        code: d.detail.code || 'error',
        message: d.detail.message || fallback,
      }
    }
    if (typeof d.detail === 'string') {
      return { code: 'error', message: d.detail }
    }
    if (d.message) {
      return { code: d.code || 'error', message: d.message }
    }
  }
  return { code: 'error', message: fallback }
}

function mergeAbortSignals(
  timeoutMs: number,
  external?: AbortSignal | null,
): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  const onExternalAbort = () => controller.abort()
  if (external) {
    if (external.aborted) controller.abort()
    else external.addEventListener('abort', onExternalAbort, { once: true })
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer)
      external?.removeEventListener('abort', onExternalAbort)
    },
  }
}

async function hiFetch<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal: external, ...rest } = init
  const { signal, cleanup } = mergeAbortSignals(timeoutMs, external ?? null)
  const url = `${HI_API_BASE}${path}`

  let res: Response
  try {
    res = await fetch(url, { credentials: 'include', ...rest, signal })
  } catch (err) {
    cleanup()
    if (external?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
      throw {
        code: 'aborted',
        message: 'Запрос отменён.',
      } satisfies HotelIntelligenceApiError
    }
    throw {
      code: 'network_unavailable',
      message:
        'Сервер О!Подбор недоступен. Проверьте, что backend запущен на :8000.',
    } satisfies HotelIntelligenceApiError
  }

  const data = await res.json().catch(() => null)
  cleanup()

  if (!res.ok) {
    throw parseHotelIntelligenceError(data, `Ошибка сервера (${res.status})`)
  }
  return data as T
}

export async function fetchIntelligenceStatus(
  signal?: AbortSignal,
): Promise<IntelligenceStatus> {
  return hiFetch<IntelligenceStatus>('/api/hotel-intelligence/status', {
    signal,
    timeoutMs: 8_000,
  })
}

export async function fetchAttributes(
  signal?: AbortSignal,
): Promise<AttributeDefinition[]> {
  const data = await hiFetch<{ attributes: AttributeDefinition[] }>(
    '/api/hotel-intelligence/attributes',
    { signal },
  )
  return Array.isArray(data.attributes) ? data.attributes : []
}

export async function fetchIntelligenceHotels(
  signal?: AbortSignal,
): Promise<IntelligenceHotel[]> {
  const data = await hiFetch<{ hotels: IntelligenceHotel[] }>(
    '/api/hotel-intelligence/hotels',
    { signal },
  )
  return Array.isArray(data.hotels) ? data.hotels : []
}

export async function fetchIntelligenceHotel(
  hotelId: string,
  signal?: AbortSignal,
): Promise<IntelligenceHotel> {
  const data = await hiFetch<{ hotel: IntelligenceHotel }>(
    `/api/hotel-intelligence/hotels/${encodeURIComponent(hotelId)}`,
    { signal },
  )
  return data.hotel
}

export async function fetchHotelEvidence(
  hotelId: string,
  attributeKey?: string,
  signal?: AbortSignal,
): Promise<{ hotel_id: string; observations: AttributeObservation[] }> {
  const qs = attributeKey
    ? `?attribute_key=${encodeURIComponent(attributeKey)}`
    : ''
  return hiFetch(`/api/hotel-intelligence/hotels/${encodeURIComponent(hotelId)}/evidence${qs}`, {
    signal,
  })
}

export type SearchHotelsOptions = {
  limit?: number
  previousQuery?: string | null
  conversation?: { role: string; content: string }[]
  preferGigaChat?: boolean
  explain?: boolean
  signal?: AbortSignal
}

export async function searchHotels(
  query: string,
  limitOrOpts: number | SearchHotelsOptions = 20,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const opts: SearchHotelsOptions =
    typeof limitOrOpts === 'number'
      ? { limit: limitOrOpts, signal }
      : limitOrOpts
  const data = await hiFetch<SearchResponse>('/api/hotel-intelligence/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      limit: opts.limit ?? 20,
      previous_query: opts.previousQuery ?? null,
      conversation: opts.conversation ?? null,
      prefer_gigachat: opts.preferGigaChat ?? true,
      explain: opts.explain ?? false,
    }),
    signal: opts.signal ?? signal,
    timeoutMs: SEARCH_TIMEOUT_MS,
  })
  return {
    query: data.query ?? query,
    extraction: data.extraction,
    city: data.city,
    unsupported: data.unsupported,
    requested: Array.isArray(data.requested) ? data.requested : [],
    results: Array.isArray(data.results) ? data.results : [],
    previous_query: data.previous_query,
    note: data.note,
  }
}

export async function enrichHotel(
  hotelId: string,
  attributes?: string[],
  signal?: AbortSignal,
): Promise<EnrichResponse> {
  await ensureDemoSession(signal)
  return hiFetch<EnrichResponse>('/api/hotel-intelligence/enrich', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...HI_DEMO_MUTATION_HEADER },
    body: JSON.stringify({ hotel_id: hotelId, attributes: attributes ?? null }),
    signal,
    timeoutMs: ENRICH_TIMEOUT_MS,
  })
}

export async function fetchHotelierQuestions(opts?: {
  hotelId?: string
  status?: string
  signal?: AbortSignal
}): Promise<HotelierQuestion[]> {
  const params = new URLSearchParams()
  if (opts?.hotelId) params.set('hotel_id', opts.hotelId)
  if (opts?.status) params.set('status', opts.status)
  const qs = params.toString() ? `?${params}` : ''
  const data = await hiFetch<{ questions: HotelierQuestion[] }>(
    `/api/hotel-intelligence/hotelier/questions${qs}`,
    { signal: opts?.signal },
  )
  return Array.isArray(data.questions) ? data.questions : []
}

export async function answerHotelierQuestion(
  questionId: string,
  rawText: string,
  opts?: { simulated?: boolean; allowGigaChat?: boolean; signal?: AbortSignal },
): Promise<{
  question_id: string
  observations: AttributeObservation[]
  trace: { agent: string; steps: unknown[] }
}> {
  await ensureDemoSession(opts?.signal)
  // Client cannot escalate to official hotelier — always simulated in demo UI.
  return hiFetch(`/api/hotel-intelligence/hotelier/questions/${encodeURIComponent(questionId)}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...HI_DEMO_MUTATION_HEADER },
    body: JSON.stringify({
      raw_text: rawText,
      simulated: true,
      allow_gigachat: opts?.allowGigaChat ?? true,
    }),
    signal: opts?.signal,
    timeoutMs: 60_000,
  })
}

export async function fetchConflicts(opts?: {
  hotelId?: string
  status?: string
  signal?: AbortSignal
}): Promise<ConflictRecord[]> {
  const params = new URLSearchParams()
  if (opts?.hotelId) params.set('hotel_id', opts.hotelId)
  if (opts?.status) params.set('status', opts.status)
  const qs = params.toString() ? `?${params}` : ''
  const data = await hiFetch<{ conflicts: ConflictRecord[] }>(
    `/api/hotel-intelligence/conflicts${qs}`,
    { signal: opts?.signal },
  )
  return Array.isArray(data.conflicts) ? data.conflicts : []
}

export async function resolveConflict(
  conflictId: string,
  body: { note?: string; preferred_observation_id?: string | null },
  signal?: AbortSignal,
): Promise<{ ok: boolean }> {
  await ensureDemoSession(signal)
  return hiFetch(`/api/hotel-intelligence/conflicts/${encodeURIComponent(conflictId)}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...HI_DEMO_MUTATION_HEADER },
    body: JSON.stringify(body),
    signal,
  })
}

export function hotelLatLon(
  hotel: IntelligenceHotel | null | undefined,
): { lat: number; lon: number } | null {
  if (!hotel) return null
  const lat = hotel.lat ?? hotel.latitude
  const lon = hotel.lon ?? hotel.longitude
  if (typeof lat !== 'number' || typeof lon !== 'number') return null
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  return { lat, lon }
}

export function hotelDisplayName(hotel: IntelligenceHotel | null | undefined): string {
  if (!hotel) return 'Отель'
  return String(hotel.name || hotel.canonical_name || hotel.hotel_id || hotel.id || 'Отель')
}
