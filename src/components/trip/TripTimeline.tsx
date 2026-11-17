import { useState } from 'react'
import { motion } from 'framer-motion'
import type { DayPlan, TravelSegment, TripStop } from '../../types/trip'
import { useMotionProfile } from '../../motion/useMotionProfile'
import { springs } from '../../motion/tokens'

type Props = {
  day: DayPlan
  selectedStopId: string | null
  onSelectStop: (id: string) => void
}

const CATEGORY_PLACEHOLDER: Record<string, string> = {
  museum: 'Музей',
  beach: 'Пляж',
  restaurant: 'Ресторан',
  bar: 'Бар',
  park: 'Парк',
  attraction: 'Место',
  viewpoint: 'Смотровая',
  religious: 'Храм',
}

function formatTravel(seg: TravelSegment): string {
  if (seg.verified === false) {
    return 'маршрут не подтверждён'
  }
  const km = (seg.distanceMeters / 1000).toFixed(1).replace('.', ',')
  const mins = Math.max(1, Math.round(seg.durationSeconds / 60))
  const mode =
    seg.mode === 'car' ? 'на машине' : seg.mode === 'transit' ? 'транспортом' : 'пешком'
  return `${km} км · ${mins} мин ${mode}`
}

function StopPhoto({ stop }: { stop: TripStop }) {
  const [failed, setFailed] = useState(false)
  const label = CATEGORY_PLACEHOLDER[stop.category] || 'Место'
  const src = stop.photoUrl && !failed ? stop.photoUrl : null

  if (src) {
    return (
      <img
        src={src}
        alt=""
        loading="lazy"
        decoding="async"
        className="h-[84px] w-[84px] shrink-0 rounded-2xl object-cover bg-brand-green-100"
        onError={() => setFailed(true)}
      />
    )
  }
  return (
    <div className="flex h-[84px] w-[84px] shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-green-100 to-brand-green-200 text-xs font-semibold text-brand-blue-900">
      {label}
    </div>
  )
}

export function TripTimeline({ day, selectedStopId, onSelectStop }: Props) {
  const profile = useMotionProfile()

  return (
    <div className="space-y-0">
      {day.stops.map((stop, index) => {
        const fromHotel =
          index === 0 ? day.segments.find((s) => s.fromStopId === 'hotel' && s.toStopId === stop.id) : null
        const seg = day.segments.find((s) => s.fromStopId === stop.id)
        const selected = selectedStopId === stop.id
        return (
          <motion.div
            key={stop.id}
            initial={profile.reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={profile.reduce ? { duration: 0.12 } : { ...springs.gentle, delay: Math.min(index, 6) * 0.04 }}
          >
            {fromHotel ? (
              <div className="flex items-center gap-2 py-2 pl-6 text-xs font-medium text-text-secondary">
                <span className="h-6 w-px bg-border" aria-hidden />
                <span>От отеля · {formatTravel(fromHotel)}</span>
              </div>
            ) : null}
            <button
              type="button"
              onClick={() => onSelectStop(stop.id)}
              className={`flex w-full gap-3 rounded-[18px] border p-3 text-left transition-[border-color,background-color,box-shadow] duration-200 ${
                selected
                  ? 'border-brand-blue-800 bg-brand-green-100 shadow-sm'
                  : 'border-border bg-white hover:border-brand-green-400'
              }`}
            >
              <StopPhoto stop={stop} />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[15px] font-bold text-brand-blue-950">
                    {index + 1}. {stop.name}
                  </p>
                  <span className="shrink-0 text-xs font-semibold text-brand-blue-800">
                    {stop.startTime || 'время неизвестно'}
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-text-secondary">{stop.description}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-text-muted">
                  <span>{CATEGORY_PLACEHOLDER[stop.category] || stop.category}</span>
                  <span>· {stop.durationMinutes} мин</span>
                  {stop.rating != null ? <span>· ★ {stop.rating}</span> : null}
                </div>
              </div>
            </button>
            {seg && seg.toStopId !== 'hotel' ? (
              <div className="flex items-center gap-2 py-2 pl-6 text-xs font-medium text-text-secondary">
                <span className="h-6 w-px bg-border" aria-hidden />
                <span>{formatTravel(seg)}</span>
              </div>
            ) : null}
            {seg && seg.toStopId === 'hotel' ? (
              <div className="py-2 pl-6 text-xs font-medium text-text-secondary">
                ↓ Возврат в отель · {formatTravel(seg)}
              </div>
            ) : null}
          </motion.div>
        )
      })}
      {day.stops.length === 0 || day.incomplete ? (
        <p className="rounded-[18px] border border-border bg-surface-soft p-4 text-sm text-text-secondary">
          {day.incomplete || day.stops.length === 0
            ? 'Неполный результат: в этом дне нет подтверждённых остановок.'
            : null}
        </p>
      ) : null}
    </div>
  )
}
