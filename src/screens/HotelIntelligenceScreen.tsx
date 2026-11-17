import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowRight,
  Building2,
  GitCompare,
  MapPin,
  Search,
  Sparkles,
  X,
} from 'lucide-react'
import { getHotelById } from '../data/hotels'
import { ensureCatalogReady, getCatalogHotelById } from '../data/catalogHotels'
import {
  fetchAttributes,
  fetchHotelEvidence,
  fetchIntelligenceHotels,
  fetchIntelligenceStatus,
  hotelLatLon,
  searchHotels,
} from '../features/hotelIntelligence/api'
import type {
  AttributeDefinition,
  AttributeObservation,
  HotelIntelligenceApiError,
  IntelligenceHotel,
  SearchHotelResult,
  SearchResponse,
} from '../features/hotelIntelligence/types'
import { attributeLabel, catalogCoverUrl } from '../features/hotelIntelligence/labels'
import { ResultCard } from '../features/hotelIntelligence/components/ResultCard'
import { EvidenceList } from '../features/hotelIntelligence/components/EvidenceList'
import { IntelligenceMap } from '../features/hotelIntelligence/components/IntelligenceMap'
import {
  ProgressSteps,
  type ProgressStep,
} from '../features/hotelIntelligence/components/ProgressSteps'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

const exampleQueries = [
  'Тихий номер с плотными шторами, 10 минут пешком до метро',
  'Отель с детьми, рядом круглосуточная аптека',
  'Стамбул, спокойный отель недалеко от метро',
  'А теперь только с метро до 10 минут',
]

const popularCities = ['Стамбул', 'Казань', 'Москва', 'Сочи']

type UiPhase = 'idle' | 'searching' | 'ready' | 'error'

function isApiError(err: unknown): err is HotelIntelligenceApiError {
  return Boolean(err && typeof err === 'object' && 'code' in err && 'message' in err)
}

/**
 * О!Подбор — grounded hotel search. Traveler UI inspired by booking search
 * patterns; Vera Labs brand; hotelier cabinet kept off the primary path.
 */
export function HotelIntelligenceScreen() {
  const [searchParams] = useSearchParams()
  const hotelId = searchParams.get('hotelId')
  const profile = useMotionProfile()
  const abortRef = useRef<AbortController | null>(null)

  const [catalogReady, setCatalogReady] = useState(false)
  const [query, setQuery] = useState('')
  const [previousQuery, setPreviousQuery] = useState<string | null>(null)
  const [phase, setPhase] = useState<UiPhase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [apiOk, setApiOk] = useState<boolean | null>(null)
  const [gigaOk, setGigaOk] = useState(false)
  const [attributes, setAttributes] = useState<AttributeDefinition[]>([])
  const [intelHotels, setIntelHotels] = useState<IntelligenceHotel[]>([])
  const [search, setSearch] = useState<SearchResponse | null>(null)
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set())
  const [selectedHotelId, setSelectedHotelId] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<AttributeObservation[]>([])
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [steps, setSteps] = useState<ProgressStep[]>([])

  useEffect(() => {
    let active = true
    void ensureCatalogReady().then(() => {
      if (active) setCatalogReady(true)
    })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    void (async () => {
      try {
        const status = await fetchIntelligenceStatus(ac.signal)
        if (ac.signal.aborted) return
        setApiOk(Boolean(status.ok))
        setGigaOk(Boolean(status.gigachat_configured))
        const [attrs, hotels] = await Promise.all([
          fetchAttributes(ac.signal),
          fetchIntelligenceHotels(ac.signal),
        ])
        if (ac.signal.aborted) return
        setAttributes(attrs)
        setIntelHotels(hotels)
      } catch (err) {
        if (ac.signal.aborted) return
        setApiOk(false)
        if (isApiError(err) && err.code !== 'aborted') {
          setError(err.message)
        }
      }
    })()
    return () => ac.abort()
  }, [])

  const selectedHotel = hotelId
    ? getHotelById(hotelId) ?? (catalogReady ? getCatalogHotelById(hotelId) : undefined)
    : undefined

  const hotelIndex = useMemo(() => {
    const map = new Map<string, IntelligenceHotel>()
    for (const h of intelHotels) {
      map.set(h.hotel_id, h)
      if (h.id) map.set(String(h.id), h)
    }
    return map
  }, [intelHotels])

  const showcaseHotels = useMemo(() => {
    return intelHotels.slice(0, 8).map((h) => {
      const cat = catalogReady ? getCatalogHotelById(h.hotel_id) : undefined
      return {
        id: h.hotel_id,
        name: cat?.name || h.name || h.hotel_id,
        city: h.city || cat?.city || '',
        cover: catalogCoverUrl(cat),
      }
    })
  }, [intelHotels, catalogReady])

  const filteredResults = useMemo(() => {
    const results = search?.results ?? []
    if (!activeFilters.size) return results
    return results.filter((r) => {
      const keys = new Set([
        ...r.matched.map((m) => m.attribute_key),
        ...r.unmatched.map((m) => m.attribute_key),
        ...r.unknown.map((m) => m.attribute_key),
      ])
      for (const f of activeFilters) {
        if (!keys.has(f)) return false
      }
      return true
    })
  }, [search, activeFilters])

  const mapHotels = useMemo(() => {
    return filteredResults
      .map((r) => {
        const intel = hotelIndex.get(r.hotel_id)
        const catalog = catalogReady ? getCatalogHotelById(r.hotel_id) : undefined
        const coords =
          hotelLatLon(intel) ||
          (catalog &&
          typeof catalog.latitude === 'number' &&
          typeof catalog.longitude === 'number'
            ? { lat: catalog.latitude, lon: catalog.longitude }
            : null)
        if (!coords) return null
        return {
          id: r.hotel_id,
          name: r.name || catalog?.name || intel?.name || r.hotel_id,
          lat: coords.lat,
          lon: coords.lon,
        }
      })
      .filter(Boolean) as { id: string; name: string; lat: number; lon: number }[]
  }, [filteredResults, hotelIndex, catalogReady])

  useEffect(() => {
    if (!selectedHotelId) {
      setEvidence([])
      return
    }
    const ac = new AbortController()
    setEvidenceLoading(true)
    setEvidence([])
    void fetchHotelEvidence(selectedHotelId, undefined, ac.signal)
      .then((data) => {
        if (!ac.signal.aborted) setEvidence(data.observations)
      })
      .catch(() => {
        if (!ac.signal.aborted) setEvidence([])
      })
      .finally(() => {
        if (!ac.signal.aborted) setEvidenceLoading(false)
      })
    return () => ac.abort()
  }, [selectedHotelId])

  const runSearch = useCallback(
    async (raw: string, opts?: { asRefinement?: boolean }) => {
      const q = raw.trim()
      if (!q) return
      abortRef.current?.abort()
      const ac = new AbortController()
      abortRef.current = ac
      setPhase('searching')
      setError(null)
      setSearch(null)
      setSelectedHotelId(null)
      setEvidence([])
      setSteps([
        {
          id: 'parse',
          label: gigaOk ? 'Понимаем запрос (GigaChat)' : 'Разбираем запрос',
          status: 'active',
        },
        { id: 'match', label: 'Сверяем с доказательствами', status: 'pending' },
        { id: 'rank', label: 'Ранжируем без догадок', status: 'pending' },
      ])

      try {
        await new Promise((r) => setTimeout(r, profile.reduce ? 0 : 120))
        if (ac.signal.aborted) return
        setSteps((prev) =>
          prev.map((s) =>
            s.id === 'parse'
              ? { ...s, status: 'done' }
              : s.id === 'match'
                ? { ...s, status: 'active' }
                : s,
          ),
        )

        const prev =
          opts?.asRefinement && previousQuery
            ? previousQuery
            : search?.query || previousQuery

        const data = await searchHotels(q, {
          limit: 20,
          previousQuery: opts?.asRefinement ? prev : null,
          preferGigaChat: true,
          signal: ac.signal,
        })
        if (ac.signal.aborted) return

        setSteps([
          { id: 'parse', label: 'Запрос понят', status: 'done' },
          { id: 'match', label: 'Доказательства сверены', status: 'done' },
          { id: 'rank', label: 'Список готов', status: 'done' },
        ])
        setSearch(data)
        setPreviousQuery(data.query)
        setPhase('ready')
        setApiOk(true)
        const first = data.results[0]
        if (first) setSelectedHotelId(first.hotel_id)
      } catch (err) {
        if (ac.signal.aborted) return
        setPhase('error')
        setSteps((prev) =>
          prev.map((s) =>
            s.status === 'active' || s.status === 'pending'
              ? { ...s, status: 'error' }
              : s,
          ),
        )
        setError(
          isApiError(err)
            ? err.message
            : 'Не удалось выполнить поиск. Попробуйте ещё раз.',
        )
        setApiOk(false)
      }
    },
    [profile.reduce, gigaOk, previousQuery, search?.query],
  )

  const cancelSearch = () => {
    abortRef.current?.abort()
    setPhase(search ? 'ready' : 'idle')
    setSteps([])
  }

  const toggleFilter = (key: string) => {
    setActiveFilters((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const filterKeys = useMemo(() => {
    if (attributes.length) return attributes.map((a) => a.key)
    const fromSearch = new Set<string>()
    for (const r of search?.results ?? []) {
      for (const bucket of [r.matched, r.unmatched, r.unknown]) {
        for (const item of bucket) fromSearch.add(item.attribute_key)
      }
    }
    return [...fromSearch]
  }, [attributes, search])

  return (
    <main className="page-container pb-16">
      <section className="mx-auto max-w-6xl pt-8 sm:pt-10">
        {/* Compact brand + tools */}
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-brand-blue-950">
            <Sparkles size={18} className="text-brand-blue-800" aria-hidden />
            <h1 className="text-xl font-extrabold tracking-tight sm:text-2xl">О!Подбор</h1>
            <span className="hidden text-sm font-medium text-text-muted sm:inline">
              умный поиск отеля под ваши условия
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Link
              to="/hotel-intelligence/compare"
              className="inline-flex items-center gap-1.5 font-medium text-brand-blue-950 no-underline hover:underline"
            >
              <GitCompare size={14} aria-hidden /> Сравнить
            </Link>
            <Link
              to="/oh-route"
              className="font-medium text-text-secondary no-underline hover:text-brand-blue-950 hover:underline"
            >
              О!Маршрут
            </Link>
          </div>
        </div>

        {hotelId ? (
          <aside
            className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-surface-soft px-4 py-3"
            aria-label="Выбранный отель"
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-brand-blue-800">
                Из каталога
              </p>
              <p className="text-base font-bold text-brand-blue-950">
                {selectedHotel?.name ??
                  (catalogReady ? 'Отель не найден' : 'Загрузка…')}
              </p>
            </div>
            <Link
              to={`/hotel-intelligence/hotel/${encodeURIComponent(hotelId)}`}
              className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-border bg-white px-4 py-2 text-sm font-semibold text-brand-blue-950 no-underline hover:bg-white"
            >
              <Building2 size={15} aria-hidden /> Карточка
            </Link>
          </aside>
        ) : null}

        {apiOk === false && phase === 'idle' && error ? (
          <p
            className="mb-4 rounded-xl border border-border bg-error-bg/40 px-4 py-3 text-sm text-error"
            role="status"
          >
            {error}
          </p>
        ) : null}

        {/* Dominant search bar */}
        <form
          className="rounded-2xl border border-border bg-white p-3 shadow-sm sm:p-4"
          onSubmit={(e) => {
            e.preventDefault()
            void runSearch(query, { asRefinement: Boolean(previousQuery && search) })
          }}
          aria-label="Поиск отеля"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
            <label className="relative min-w-0 flex-1">
              <span className="sr-only">Куда едете и что важно</span>
              <Search
                size={18}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted"
                aria-hidden
              />
              <input
                id="hotel-intelligence-query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                maxLength={1000}
                placeholder="Город, метро, тишина, blackout, аптека…"
                className="h-12 w-full rounded-xl border border-border bg-surface-soft pl-10 pr-3 text-base text-text-primary outline-none focus:border-brand-blue-800"
                autoComplete="off"
              />
            </label>
            <div className="flex gap-2">
              {phase === 'searching' ? (
                <button
                  type="button"
                  onClick={cancelSearch}
                  className="inline-flex h-12 min-w-[7rem] items-center justify-center gap-2 rounded-xl border border-border bg-white px-4 text-sm font-semibold text-brand-blue-950"
                >
                  <X size={16} aria-hidden /> Отмена
                </button>
              ) : null}
              <button
                type="submit"
                disabled={!query.trim() || phase === 'searching'}
                className="inline-flex h-12 min-w-[8.5rem] flex-1 items-center justify-center gap-2 rounded-xl bg-brand-blue-950 px-5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none"
              >
                {phase === 'searching' ? 'Ищем…' : 'Найти'}
              </button>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-2" aria-label="Направления">
            {popularCities.map((city) => (
              <button
                key={city}
                type="button"
                onClick={() => {
                  const next = query.trim()
                    ? `${city}, ${query.trim()}`
                    : `Отель в ${city} рядом с метро`
                  setQuery(next)
                }}
                className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-soft"
              >
                <MapPin size={12} aria-hidden /> {city}
              </button>
            ))}
          </div>

          <div className="mt-2 flex flex-wrap gap-2" aria-label="Примеры запросов">
            {exampleQueries.map((sample) => (
              <button
                key={sample}
                type="button"
                onClick={() => {
                  setQuery(sample)
                  const refine = sample.toLowerCase().startsWith('а теперь')
                  void runSearch(sample, { asRefinement: refine })
                }}
                className="rounded-lg border border-dashed border-border px-2.5 py-1.5 text-left text-xs text-text-secondary hover:bg-surface-soft"
              >
                {sample}
              </button>
            ))}
          </div>
        </form>

        {phase === 'searching' || (phase === 'error' && steps.length) ? (
          <div className="mt-5">
            <ProgressSteps steps={steps} title="Ход исследования" />
          </div>
        ) : null}

        {phase === 'error' && error ? (
          <div className="mt-5 rounded-2xl border border-border bg-error-bg/30 p-5" role="alert">
            <p className="text-sm font-semibold text-error">{error}</p>
            <button
              type="button"
              className="mt-3 inline-flex min-h-10 items-center rounded-full border border-border bg-white px-4 py-2 text-sm font-semibold text-brand-blue-950"
              onClick={() => void runSearch(query)}
            >
              Повторить
            </button>
          </div>
        ) : null}

        {phase === 'ready' && search ? (
          <motion.div
            className="mt-6"
            initial={profile.reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={profile.reduce ? { duration: 0 } : springs.gentle}
          >
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-brand-blue-950 sm:text-2xl">
                  {filteredResults.length} вариантов
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  «{search.query}»
                  {search.extraction === 'gigachat' ? ' · понято через GigaChat' : ''}
                  {search.requested.length
                    ? ` · ${search.requested.map((r) => attributeLabel(r.key)).join(', ')}`
                    : ''}
                </p>
                {search.unsupported?.length ? (
                  <p className="mt-1 text-xs text-text-muted">
                    Часть условий пока нельзя проверить по доступным данным.
                  </p>
                ) : null}
              </div>
              {previousQuery ? (
                <button
                  type="button"
                  className="text-xs font-medium text-brand-blue-800 underline"
                  onClick={() => {
                    setQuery('')
                    setPreviousQuery(null)
                  }}
                >
                  Новый поиск
                </button>
              ) : null}
            </div>

            {filterKeys.length ? (
              <div className="mb-4 flex flex-wrap gap-2" aria-label="Фильтры">
                {filterKeys.map((key) => {
                  const on = activeFilters.has(key)
                  return (
                    <button
                      key={key}
                      type="button"
                      aria-pressed={on}
                      onClick={() => toggleFilter(key)}
                      className={[
                        'rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
                        on
                          ? 'border-brand-blue-800 bg-brand-blue-950 text-white'
                          : 'border-border bg-white text-text-secondary hover:bg-surface-soft',
                      ].join(' ')}
                    >
                      {attributeLabel(key)}
                    </button>
                  )
                })}
              </div>
            ) : null}

            {!filteredResults.length ? (
              <p className="rounded-2xl border border-dashed border-border bg-surface-soft p-6 text-sm text-text-secondary">
                {search.requested.length === 0
                  ? 'Не удалось распознать условия. Попробуйте пример или уточните формулировку.'
                  : 'Нет отелей под выбранные фильтры. Снимите фильтры или уточните запрос.'}
              </p>
            ) : (
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(280px,0.9fr)]">
                <div className="flex flex-col gap-4">
                  {filteredResults.map((result: SearchHotelResult) => {
                    const catalog = catalogReady
                      ? getCatalogHotelById(result.hotel_id)
                      : undefined
                    const intel = hotelIndex.get(result.hotel_id)
                    return (
                      <ResultCard
                        key={result.hotel_id}
                        result={result}
                        catalogHotel={catalog}
                        district={
                          [intel?.city || catalog?.city, intel?.region || catalog?.country]
                            .filter(Boolean)
                            .join(' · ') || null
                        }
                        selected={selectedHotelId === result.hotel_id}
                        onSelect={() => setSelectedHotelId(result.hotel_id)}
                      />
                    )
                  })}
                </div>
                <div className="flex flex-col gap-4 lg:sticky lg:top-20 lg:self-start">
                  <IntelligenceMap
                    hotels={mapHotels}
                    selectedId={selectedHotelId}
                    onSelect={setSelectedHotelId}
                  />
                  <section aria-labelledby="evidence-panel-title">
                    <h3
                      id="evidence-panel-title"
                      className="mb-3 text-sm font-bold text-brand-blue-950"
                    >
                      Источники
                    </h3>
                    {evidenceLoading ? (
                      <div
                        className="h-32 animate-pulse rounded-2xl border border-border bg-surface-soft"
                        aria-busy="true"
                      />
                    ) : (
                      <EvidenceList
                        observations={evidence.slice(0, 8)}
                        emptyMessage={
                          selectedHotelId
                            ? 'Пока нет сохранённых наблюдений.'
                            : 'Выберите отель, чтобы увидеть доказательства.'
                        }
                      />
                    )}
                  </section>
                </div>
              </div>
            )}
          </motion.div>
        ) : null}

        {phase === 'idle' && !search ? (
          <section className="mt-8" aria-labelledby="picks-title">
            <div className="mb-4 flex items-end justify-between gap-3">
              <h2 id="picks-title" className="text-lg font-bold text-brand-blue-950 sm:text-xl">
                Отели в подборке
              </h2>
              <Link
                to="/catalog"
                className="inline-flex items-center gap-1 text-sm font-medium text-brand-blue-950 no-underline hover:underline"
              >
                Каталог <ArrowRight size={14} aria-hidden />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
              {showcaseHotels.map((h) => (
                <Link
                  key={h.id}
                  to={`/hotel-intelligence/hotel/${encodeURIComponent(h.id)}`}
                  className="group overflow-hidden rounded-2xl border border-border bg-white no-underline shadow-sm"
                >
                  <div className="aspect-[4/3] bg-surface-soft">
                    {h.cover ? (
                      <img
                        src={h.cover}
                        alt=""
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-text-muted">
                        Нет фото
                      </div>
                    )}
                  </div>
                  <div className="p-2.5">
                    <p className="truncate text-sm font-semibold text-brand-blue-950">{h.name}</p>
                    {h.city ? (
                      <p className="mt-0.5 truncate text-xs text-text-secondary">{h.city}</p>
                    ) : null}
                  </div>
                </Link>
              ))}
            </div>
            <p className="mt-6 text-center text-xs text-text-muted">
              Для отельеров:{' '}
              <Link
                to="/hotel-intelligence/hotelier"
                className="text-text-secondary underline hover:text-brand-blue-950"
              >
                кабинет ответов
              </Link>
              {' · '}симулированные ответы всегда помечены
            </p>
          </section>
        ) : null}
      </section>
    </main>
  )
}
