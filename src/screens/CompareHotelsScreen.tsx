import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, GitCompare } from 'lucide-react'
import {
  fetchAttributes,
  fetchHotelEvidence,
  fetchIntelligenceHotels,
  hotelDisplayName,
} from '../features/hotelIntelligence/api'
import type {
  AttributeDefinition,
  AttributeObservation,
  HotelIntelligenceApiError,
  IntelligenceHotel,
} from '../features/hotelIntelligence/types'
import {
  CompareTable,
  type CompareColumn,
} from '../features/hotelIntelligence/components/CompareTable'

function isApiError(err: unknown): err is HotelIntelligenceApiError {
  return Boolean(err && typeof err === 'object' && 'code' in err && 'message' in err)
}

function parseIds(raw: string | null): string[] {
  if (!raw) return []
  return [...new Set(raw.split(',').map((s) => s.trim()).filter(Boolean))].slice(0, 3)
}

export function CompareHotelsScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedIds = useMemo(
    () => parseIds(searchParams.get('ids')),
    [searchParams],
  )

  const [hotels, setHotels] = useState<IntelligenceHotel[]>([])
  const [attributes, setAttributes] = useState<AttributeDefinition[]>([])
  const [columns, setColumns] = useState<CompareColumn[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pick, setPick] = useState('')

  useEffect(() => {
    const ac = new AbortController()
    void (async () => {
      try {
        const [hs, attrs] = await Promise.all([
          fetchIntelligenceHotels(ac.signal),
          fetchAttributes(ac.signal),
        ])
        if (ac.signal.aborted) return
        setHotels(hs)
        setAttributes(attrs)
      } catch (err) {
        if (ac.signal.aborted) return
        setError(isApiError(err) ? err.message : 'Не удалось загрузить список отелей')
      } finally {
        if (!ac.signal.aborted) setLoading(false)
      }
    })()
    return () => ac.abort()
  }, [])

  useEffect(() => {
    if (!selectedIds.length) {
      setColumns([])
      return
    }
    const ac = new AbortController()
    void (async () => {
      setError(null)
      try {
        const cols: CompareColumn[] = []
        for (const id of selectedIds) {
          const hotel =
            hotels.find((h) => h.hotel_id === id || h.id === id) ??
            ({ hotel_id: id, name: id } as IntelligenceHotel)
          let observations: AttributeObservation[] = []
          try {
            const ev = await fetchHotelEvidence(id, undefined, ac.signal)
            observations = ev.observations
          } catch {
            observations = []
          }
          cols.push({ hotel, observations })
        }
        if (!ac.signal.aborted) setColumns(cols)
      } catch (err) {
        if (ac.signal.aborted) return
        setError(isApiError(err) ? err.message : 'Ошибка сравнения')
      }
    })()
    return () => ac.abort()
  }, [selectedIds, hotels])

  const attributeKeys = useMemo(() => {
    if (attributes.length) return attributes.map((a) => a.key)
    const keys = new Set<string>()
    for (const col of columns) {
      for (const o of col.observations) keys.add(o.attribute_key)
    }
    return [...keys]
  }, [attributes, columns])

  const setIds = (ids: string[]) => {
    const next = [...new Set(ids)].slice(0, 3)
    if (!next.length) {
      setSearchParams({})
      return
    }
    setSearchParams({ ids: next.join(',') })
  }

  const addHotel = (id: string) => {
    if (!id || selectedIds.includes(id) || selectedIds.length >= 3) return
    setIds([...selectedIds, id])
    setPick('')
  }

  const removeHotel = (id: string) => {
    setIds(selectedIds.filter((x) => x !== id))
  }

  return (
    <main className="page-container pb-20 pt-10 sm:pt-14">
      <Link
        to="/hotel-intelligence"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-blue-950 no-underline hover:underline"
      >
        <ArrowLeft size={16} aria-hidden /> К О!Подбор
      </Link>

      <header className="mt-6 max-w-3xl">
        <div className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-brand-blue-800">
          <GitCompare size={17} aria-hidden />
          Сравнение отелей
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-brand-blue-950 sm:text-4xl">
          2–3 отеля рядом
        </h1>
        <p className="mt-3 text-sm leading-6 text-text-secondary sm:text-base">
          Сравниваем только сохранённые наблюдения: шум, пешая доступность, POI, данные отельера,
          источники и свежесть. Факты здания и номера разделены.
        </p>
      </header>

      <section className="mt-8 rounded-[22px] border border-border bg-white p-5 shadow-sm sm:p-6">
        <label htmlFor="compare-pick" className="text-sm font-semibold text-brand-blue-950">
          Добавить отель ({selectedIds.length}/3)
        </label>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
          <select
            id="compare-pick"
            value={pick}
            disabled={loading || selectedIds.length >= 3}
            onChange={(e) => setPick(e.target.value)}
            className="min-h-11 flex-1 rounded-2xl border border-border bg-surface-soft px-3 text-sm outline-none focus:border-brand-blue-800"
          >
            <option value="">Выберите отель…</option>
            {hotels
              .filter((h) => !selectedIds.includes(h.hotel_id))
              .map((h) => (
                <option key={h.hotel_id} value={h.hotel_id}>
                  {hotelDisplayName(h)}
                </option>
              ))}
          </select>
          <button
            type="button"
            disabled={!pick || selectedIds.length >= 3}
            onClick={() => addHotel(pick)}
            className="inline-flex min-h-11 items-center justify-center rounded-full bg-brand-blue-950 px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            Добавить
          </button>
        </div>

        {selectedIds.length ? (
          <ul className="mt-4 flex flex-wrap gap-2" aria-label="Выбранные отели">
            {selectedIds.map((id) => {
              const h = hotels.find((x) => x.hotel_id === id)
              return (
                <li key={id}>
                  <button
                    type="button"
                    onClick={() => removeHotel(id)}
                    className="rounded-full border border-border bg-surface-soft px-3 py-1.5 text-xs font-medium text-brand-blue-950 hover:bg-white"
                    aria-label={`Убрать ${hotelDisplayName(h) || id}`}
                  >
                    {hotelDisplayName(h) || id} ×
                  </button>
                </li>
              )
            })}
          </ul>
        ) : null}
      </section>

      {error ? (
        <p className="mt-6 rounded-2xl border border-border bg-error-bg/30 p-4 text-sm text-error" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <div className="mt-8 h-48 animate-pulse rounded-[22px] bg-surface-soft" aria-busy="true" />
      ) : (
        <div className="mt-8">
          <CompareTable columns={columns} attributeKeys={attributeKeys} />
        </div>
      )}
    </main>
  )
}
