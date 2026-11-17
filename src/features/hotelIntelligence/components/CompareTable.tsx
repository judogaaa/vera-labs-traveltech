import {
  attributeLabel,
  claimStatusLabel,
  formatObservationValue,
  scopeLabel,
} from '../labels'
import type { AttributeObservation, IntelligenceHotel } from '../types'
import { hotelDisplayName } from '../api'

export type CompareColumn = {
  hotel: IntelligenceHotel
  observations: AttributeObservation[]
}

type Props = {
  columns: CompareColumn[]
  attributeKeys: string[]
}

function pickBest(obs: AttributeObservation[]): AttributeObservation | null {
  if (!obs.length) return null
  const rank: Record<string, number> = {
    verified: 5,
    estimated: 4,
    unconfirmed: 3,
    conflicted: 2,
    stale: 1,
    unknown: 0,
  }
  return [...obs].sort(
    (a, b) => (rank[b.status] ?? 0) - (rank[a.status] ?? 0),
  )[0]
}

function freshness(obs: AttributeObservation | null): string {
  if (!obs?.observed_at) return '—'
  const d = new Date(obs.observed_at)
  if (Number.isNaN(d.getTime())) return obs.observed_at
  return d.toLocaleDateString('ru-RU')
}

function sourceKinds(obs: AttributeObservation | null): string {
  if (!obs?.sources?.length) return 'нет источников'
  return obs.sources
    .map((s) => (s.kind === 'hotelier_simulated' ? 'симуляция отельера' : s.kind))
    .join(', ')
}

export function CompareTable({ columns, attributeKeys }: Props) {
  if (columns.length < 2) {
    return (
      <p className="rounded-2xl border border-dashed border-border bg-surface-soft p-4 text-sm text-text-secondary">
        Выберите 2–3 отеля для сравнения.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto rounded-[22px] border border-border bg-white shadow-sm">
      <table className="min-w-full border-collapse text-left text-sm">
        <caption className="sr-only">Сравнение атрибутов отелей О!Подбор</caption>
        <thead>
          <tr className="border-b border-border bg-surface-soft">
            <th scope="col" className="px-4 py-3 font-semibold text-brand-blue-950">
              Атрибут
            </th>
            {columns.map((col) => (
              <th
                key={col.hotel.hotel_id}
                scope="col"
                className="min-w-[10rem] px-4 py-3 font-semibold text-brand-blue-950"
              >
                {hotelDisplayName(col.hotel)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {attributeKeys.map((key) => (
            <tr key={key} className="border-b border-border align-top">
              <th
                scope="row"
                className="whitespace-nowrap px-4 py-3 font-medium text-text-primary"
              >
                {attributeLabel(key)}
              </th>
              {columns.map((col) => {
                const forKey = col.observations.filter((o) => o.attribute_key === key)
                const building = forKey.filter((o) =>
                  ['hotel', 'building'].includes(o.scope.kind),
                )
                const room = forKey.filter((o) =>
                  ['room', 'room_type', 'facade'].includes(o.scope.kind),
                )
                const bestBuilding = pickBest(building)
                const bestRoom = pickBest(room)
                const best = bestBuilding || bestRoom || pickBest(forKey)

                if (!best) {
                  return (
                    <td key={col.hotel.hotel_id} className="px-4 py-3 text-text-muted">
                      неизвестно
                    </td>
                  )
                }

                return (
                  <td key={col.hotel.hotel_id} className="px-4 py-3 text-text-secondary">
                    <p className="font-medium text-brand-blue-950">
                      {formatObservationValue(key, best.value)}
                    </p>
                    <p className="mt-1 text-xs">
                      {claimStatusLabel(best.status)}
                      {best.confidence != null
                        ? ` · ${(best.confidence * 100).toFixed(0)}%`
                        : ''}
                    </p>
                    {bestBuilding && bestRoom ? (
                      <p className="mt-1 text-xs text-text-muted">
                        здание: {scopeLabel(bestBuilding.scope.kind)}; номер:{' '}
                        {scopeLabel(bestRoom.scope.kind)}
                      </p>
                    ) : (
                      <p className="mt-1 text-xs text-text-muted">
                        область: {scopeLabel(best.scope.kind)}
                        {best.scope.identifier ? ` (${best.scope.identifier})` : ''}
                      </p>
                    )}
                    <p className="mt-1 text-xs text-text-muted">
                      источники: {sourceKinds(best)} · свежесть: {freshness(best)}
                    </p>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
