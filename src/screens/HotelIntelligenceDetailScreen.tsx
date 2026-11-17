import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, GitCompare, RefreshCw } from 'lucide-react'
import { ensureCatalogReady, getCatalogHotelById } from '../data/catalogHotels'
import {
  enrichHotel,
  fetchConflicts,
  fetchHotelEvidence,
  fetchHotelierQuestions,
  fetchIntelligenceHotel,
  hotelDisplayName,
  hotelLatLon,
  resolveConflict,
} from '../features/hotelIntelligence/api'
import type {
  AttributeObservation,
  ConflictRecord,
  HotelierQuestion,
  HotelIntelligenceApiError,
  IntelligenceHotel,
} from '../features/hotelIntelligence/types'
import {
  attributeLabel,
  claimStatusLabel,
  formatObservationValue,
  scopeLabel,
} from '../features/hotelIntelligence/labels'
import { EvidenceList } from '../features/hotelIntelligence/components/EvidenceList'
import { IntelligenceMap } from '../features/hotelIntelligence/components/IntelligenceMap'
import { AttributeBadge } from '../features/hotelIntelligence/components/AttributeBadge'
import { catalogCoverUrl } from '../features/hotelIntelligence/labels'

function isApiError(err: unknown): err is HotelIntelligenceApiError {
  return Boolean(err && typeof err === 'object' && 'code' in err && 'message' in err)
}

export function HotelIntelligenceDetailScreen() {
  const { hotelId = '' } = useParams()
  const [catalogReady, setCatalogReady] = useState(false)
  const [hotel, setHotel] = useState<IntelligenceHotel | null>(null)
  const [observations, setObservations] = useState<AttributeObservation[]>([])
  const [questions, setQuestions] = useState<HotelierQuestion[]>([])
  const [conflicts, setConflicts] = useState<ConflictRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [enriching, setEnriching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void ensureCatalogReady().then(() => {
      if (active) setCatalogReady(true)
    })
    return () => {
      active = false
    }
  }, [])

  const reload = async (signal?: AbortSignal) => {
    if (!hotelId) return
    setLoading(true)
    setError(null)
    try {
      const [h, ev, qs, cs] = await Promise.all([
        fetchIntelligenceHotel(hotelId, signal),
        fetchHotelEvidence(hotelId, undefined, signal),
        fetchHotelierQuestions({ hotelId, signal }),
        fetchConflicts({ hotelId, signal }),
      ])
      if (signal?.aborted) return
      setHotel(h)
      setObservations(ev.observations)
      setQuestions(qs)
      setConflicts(cs)
    } catch (err) {
      if (signal?.aborted) return
      setError(isApiError(err) ? err.message : 'Не удалось загрузить карточку')
      setHotel(null)
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }

  useEffect(() => {
    const ac = new AbortController()
    void reload(ac.signal)
    return () => ac.abort()
  }, [hotelId])

  const catalog = catalogReady && hotelId ? getCatalogHotelById(hotelId) : undefined
  const cover = catalogCoverUrl(catalog)
  const name = catalog?.name || hotelDisplayName(hotel)
  const coords = hotelLatLon(hotel)

  const byScope = useMemo(() => {
    const building: AttributeObservation[] = []
    const room: AttributeObservation[] = []
    for (const o of observations) {
      if (['hotel', 'building'].includes(o.scope.kind)) building.push(o)
      else room.push(o)
    }
    return { building, room }
  }, [observations])

  const mapHotels = coords
    ? [{ id: hotelId, name, lat: coords.lat, lon: coords.lon }]
    : []

  return (
    <main className="page-container pb-20 pt-10 sm:pt-14">
      <Link
        to="/hotel-intelligence"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-blue-950 no-underline hover:underline"
      >
        <ArrowLeft size={16} aria-hidden /> К поиску О!Подбор
      </Link>

      {loading ? (
        <div className="mt-8 space-y-4" aria-busy="true">
          <div className="h-10 w-2/3 max-w-md animate-pulse rounded-xl bg-surface-soft" />
          <div className="h-48 animate-pulse rounded-[22px] bg-surface-soft" />
          <div className="h-64 animate-pulse rounded-[22px] bg-surface-soft" />
        </div>
      ) : error ? (
        <div className="mt-8 rounded-2xl border border-border bg-error-bg/30 p-6" role="alert">
          <p className="font-semibold text-error">{error}</p>
          <button
            type="button"
            className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-full border border-border bg-white px-4 py-2 text-sm font-semibold"
            onClick={() => void reload()}
          >
            <RefreshCw size={15} aria-hidden /> Повторить
          </button>
        </div>
      ) : (
        <>
          <header className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(240px,0.8fr)]">
            <div>
              <p className="text-sm font-semibold text-brand-blue-800">О!Подбор · доказательства</p>
              <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-brand-blue-950 sm:text-4xl">
                {name}
              </h1>
              <p className="mt-2 text-sm text-text-secondary">
                {[hotel?.city || catalog?.city, hotel?.region || catalog?.country]
                  .filter(Boolean)
                  .join(' · ') || 'Район не указан'}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={enriching}
                  className="inline-flex min-h-10 items-center gap-2 rounded-full bg-brand-blue-950 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  onClick={async () => {
                    setEnriching(true)
                    try {
                      await enrichHotel(hotelId)
                      await reload()
                    } catch (err) {
                      setError(isApiError(err) ? err.message : 'Enrichment не удался')
                    } finally {
                      setEnriching(false)
                    }
                  }}
                >
                  <RefreshCw size={15} aria-hidden />
                  {enriching ? 'Считаем…' : 'Обновить geo-evidence'}
                </button>
                <Link
                  to={`/hotel-intelligence/compare?ids=${encodeURIComponent(hotelId)}`}
                  className="inline-flex min-h-10 items-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-semibold text-brand-blue-950 no-underline hover:bg-surface-soft"
                >
                  <GitCompare size={15} aria-hidden /> Сравнить
                </Link>
                <Link
                  to={`/hotel/${encodeURIComponent(hotelId)}`}
                  className="inline-flex min-h-10 items-center rounded-full px-3 py-2 text-sm font-medium text-brand-blue-950 underline"
                >
                  В каталоге
                </Link>
              </div>
            </div>
            <div className="overflow-hidden rounded-[22px] border border-border bg-surface-soft">
              {cover ? (
                <img src={cover} alt="" className="aspect-[16/10] w-full object-cover" />
              ) : (
                <div className="flex aspect-[16/10] items-center justify-center text-sm text-text-muted">
                  Нет фото в каталоге
                </div>
              )}
            </div>
          </header>

          <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.85fr)]">
            <div className="space-y-8">
              <section aria-labelledby="attrs-title">
                <h2 id="attrs-title" className="text-xl font-bold text-brand-blue-950">
                  Атрибуты
                </h2>
                {!observations.length ? (
                  <p className="mt-3 rounded-2xl border border-dashed border-border bg-surface-soft p-4 text-sm text-text-secondary">
                    Наблюдений пока нет. Запустите enrichment или ответьте в кабинете отельера.
                  </p>
                ) : (
                  <div className="mt-4 space-y-6">
                    <div>
                      <h3 className="text-sm font-semibold text-brand-blue-800">Здание / отель</h3>
                      <ul className="mt-2 space-y-2">
                        {byScope.building.length ? (
                          byScope.building.map((o) => (
                            <li
                              key={o.observation_id}
                              className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-white px-3 py-2.5"
                            >
                              <AttributeBadge
                                attributeKey={o.attribute_key}
                                status={o.status}
                                tone="neutral"
                                valueHint={formatObservationValue(o.attribute_key, o.value)}
                              />
                              <span className="text-xs text-text-muted">
                                {scopeLabel(o.scope.kind)}
                                {o.confidence != null
                                  ? ` · ${(o.confidence * 100).toFixed(0)}%`
                                  : ''}
                              </span>
                            </li>
                          ))
                        ) : (
                          <li className="text-sm text-text-muted">Нет фактов уровня здания</li>
                        )}
                      </ul>
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-brand-blue-800">Номер / тип номера</h3>
                      <ul className="mt-2 space-y-2">
                        {byScope.room.length ? (
                          byScope.room.map((o) => (
                            <li
                              key={o.observation_id}
                              className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-white px-3 py-2.5"
                            >
                              <AttributeBadge
                                attributeKey={o.attribute_key}
                                status={o.status}
                                tone="neutral"
                                valueHint={formatObservationValue(o.attribute_key, o.value)}
                              />
                              <span className="text-xs text-text-muted">
                                {scopeLabel(o.scope.kind)}
                                {o.scope.identifier ? ` · ${o.scope.identifier}` : ''}
                              </span>
                            </li>
                          ))
                        ) : (
                          <li className="text-sm text-text-muted">
                            Нет фактов уровня номера (нужен отельер)
                          </li>
                        )}
                      </ul>
                    </div>
                  </div>
                )}
              </section>

              <section aria-labelledby="ev-title">
                <h2 id="ev-title" className="mb-3 text-xl font-bold text-brand-blue-950">
                  Источники и даты
                </h2>
                <EvidenceList observations={observations} />
              </section>

              <section aria-labelledby="conflicts-title">
                <h2 id="conflicts-title" className="text-xl font-bold text-brand-blue-950">
                  Противоречия
                </h2>
                {!conflicts.length ? (
                  <p className="mt-3 text-sm text-text-secondary">Открытых конфликтов нет.</p>
                ) : (
                  <ul className="mt-3 space-y-3">
                    {conflicts.map((c) => (
                      <li
                        key={c.conflict_id}
                        className="rounded-2xl border border-border bg-white p-4"
                      >
                        <p className="text-sm font-bold text-brand-blue-950">
                          {attributeLabel(c.attribute_key)} · {c.status}
                        </p>
                        <p className="mt-1 text-sm text-text-secondary">{c.reason}</p>
                        <p className="mt-1 text-xs text-text-muted">
                          observations: {c.observation_ids.join(', ')}
                        </p>
                        {c.status !== 'resolved' ? (
                          <button
                            type="button"
                            className="mt-3 rounded-full border border-border px-3 py-1.5 text-xs font-semibold"
                            onClick={async () => {
                              try {
                                await resolveConflict(c.conflict_id, {
                                  note: 'resolved from UI',
                                  preferred_observation_id: c.observation_ids[0] ?? null,
                                })
                                await reload()
                              } catch (err) {
                                setError(
                                  isApiError(err) ? err.message : 'Не удалось разрешить конфликт',
                                )
                              }
                            }}
                          >
                            Разрешить (предпочтение первому)
                          </button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section aria-labelledby="hq-title">
                <h2 id="hq-title" className="text-xl font-bold text-brand-blue-950">
                  Вопросы отельеру
                </h2>
                {!questions.length ? (
                  <p className="mt-3 text-sm text-text-secondary">
                    Вопросов нет.{' '}
                    <Link to="/hotel-intelligence/hotelier" className="underline">
                      Открыть кабинет
                    </Link>
                  </p>
                ) : (
                  <ul className="mt-3 space-y-2">
                    {questions.map((q) => (
                      <li
                        key={q.question_id}
                        className="rounded-xl border border-border bg-surface-soft px-3 py-2.5 text-sm"
                      >
                        <span className="font-semibold text-brand-blue-950">{q.status}</span>
                        {' · '}
                        {q.question_text}
                      </li>
                    ))}
                    <li>
                      <Link
                        to="/hotel-intelligence/hotelier"
                        className="text-sm font-semibold text-brand-blue-950 underline"
                      >
                        Ответить в кабинете →
                      </Link>
                    </li>
                  </ul>
                )}
              </section>
            </div>

            <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
              <IntelligenceMap hotels={mapHotels} selectedId={hotelId} className="h-64 w-full" />
              <div className="rounded-2xl border border-border bg-white p-4 text-sm text-text-secondary">
                <p className="font-semibold text-brand-blue-950">Сводка статусов</p>
                <ul className="mt-2 space-y-1 text-xs">
                  {(['verified', 'estimated', 'unconfirmed', 'unknown', 'conflicted', 'stale'] as const).map(
                    (st) => {
                      const n = observations.filter((o) => o.status === st).length
                      if (!n) return null
                      return (
                        <li key={st}>
                          {claimStatusLabel(st)}: {n}
                        </li>
                      )
                    },
                  )}
                  {!observations.length ? <li>нет данных</li> : null}
                </ul>
              </div>
            </aside>
          </div>
        </>
      )}
    </main>
  )
}
