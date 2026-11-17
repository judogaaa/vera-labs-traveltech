import type { HotelMatchLevel } from '../types/vision'

const labels: Record<HotelMatchLevel, string> = {
  'very-high': 'Очень высокое совпадение',
  high: 'Высокое совпадение',
  possible: 'Возможное совпадение',
}

const styles: Record<HotelMatchLevel, string> = {
  'very-high': 'bg-brand-green-100 text-brand-blue-950',
  high: 'bg-success-bg text-success',
  possible: 'bg-warning-bg text-warning',
}

export function MatchBadge({ level }: { level: HotelMatchLevel }) {
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${styles[level]}`}>
      {labels[level]}
    </span>
  )
}
