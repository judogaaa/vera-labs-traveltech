import { Link } from 'react-router-dom'
import { ArrowRight, MapPin } from 'lucide-react'
import type { CatalogHotel } from '../../../types/catalog'
import type { SearchHotelResult } from '../types'
import { AttributeBadge } from './AttributeBadge'
import {
  catalogCoverUrl,
  formatObservationValue,
  whySelectedSummary,
} from '../labels'

export type ResultCardProps = {
  result: SearchHotelResult
  catalogHotel?: CatalogHotel | null
  district?: string | null
  selected?: boolean
  onSelect?: () => void
}

export function ResultCard({
  result,
  catalogHotel,
  district,
  selected,
  onSelect,
}: ResultCardProps) {
  const name = catalogHotel?.name || result.name || result.hotel_id
  const place =
    district ||
    [catalogHotel?.city, catalogHotel?.country].filter(Boolean).join(', ') ||
    null
  const cover = catalogCoverUrl(catalogHotel)
  const why = whySelectedSummary(result)
  const detailHref = `/hotel-intelligence/hotel/${encodeURIComponent(result.hotel_id)}`

  return (
    <article
      className={[
        'overflow-hidden rounded-[22px] border bg-white shadow-sm transition-shadow',
        selected ? 'border-brand-blue-800 shadow-md' : 'border-border',
      ].join(' ')}
      data-hotel-id={result.hotel_id}
    >
      <button
        type="button"
        className="flex w-full flex-col text-left sm:flex-row"
        onClick={onSelect}
        aria-pressed={selected}
        aria-label={`Отель ${name}`}
      >
        <div className="relative aspect-[16/10] w-full shrink-0 bg-surface-soft sm:aspect-auto sm:min-h-[9.5rem] sm:w-44 md:w-56">
          {cover ? (
            <img
              src={cover}
              alt=""
              className="h-full w-full object-cover"
              loading="lazy"
              decoding="async"
            />
          ) : (
            <div className="flex h-full min-h-[7.5rem] items-center justify-center px-3 text-center text-xs text-text-muted">
              Фото из каталога недоступно
            </div>
          )}
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-2.5 p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate text-base font-bold text-brand-blue-950 sm:text-lg">{name}</h3>
              {place ? (
                <p className="mt-1 flex items-center gap-1 text-xs text-text-secondary">
                  <MapPin size={12} aria-hidden />
                  {place}
                </p>
              ) : null}
            </div>
            <span className="rounded-full bg-surface-soft px-2.5 py-1 text-[11px] font-semibold text-brand-blue-950">
              оценка {result.score.toFixed(2)}
            </span>
          </div>

          <div className="flex flex-wrap gap-1.5" aria-label="Совпавшие условия">
            {result.matched.map((m) => (
              <AttributeBadge
                key={`m-${m.attribute_key}-${m.observation_id ?? ''}`}
                attributeKey={m.attribute_key}
                status={m.status}
                tone="matched"
                valueHint={
                  m.value !== undefined
                    ? formatObservationValue(m.attribute_key, m.value)
                    : undefined
                }
              />
            ))}
            {result.unmatched.map((m) => (
              <AttributeBadge
                key={`u-${m.attribute_key}`}
                attributeKey={m.attribute_key}
                status={m.status}
                tone="unmatched"
              />
            ))}
            {result.unknown.map((m) => (
              <AttributeBadge
                key={`k-${m.attribute_key}`}
                attributeKey={m.attribute_key}
                tone="unknown"
              />
            ))}
          </div>

          <p className="text-xs leading-5 text-text-secondary">
            <span className="font-semibold text-brand-blue-950">Почему выбран: </span>
            {why}
          </p>
        </div>
      </button>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2.5">
        <Link
          to={detailHref}
          className="inline-flex min-h-9 items-center gap-1.5 text-sm font-semibold text-brand-blue-950 no-underline hover:underline"
        >
          Доказательства <ArrowRight size={14} aria-hidden />
        </Link>
        <Link
          to={`/hotel/${encodeURIComponent(result.hotel_id)}`}
          className="text-xs font-medium text-text-secondary no-underline hover:text-brand-blue-950 hover:underline"
        >
          Карточка в каталоге
        </Link>
      </div>
    </article>
  )
}
