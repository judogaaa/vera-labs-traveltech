import { Star } from 'lucide-react'
import { formatReviews } from '../lib/format'

export function RatingBadge({
  rating,
  reviewCount,
  compact = false,
}: {
  rating: number
  reviewCount?: number
  compact?: boolean
}) {
  return (
    <div className="inline-flex items-center gap-2">
      <span className="inline-flex items-center gap-1 rounded-xl bg-brand-blue-950 px-2.5 py-1 text-sm font-semibold text-white">
        <Star size={14} fill="currentColor" aria-hidden />
        {rating.toFixed(1).replace('.', ',')}
      </span>
      {!compact && reviewCount != null ? (
        <span className="text-sm text-text-secondary">{formatReviews(reviewCount)}</span>
      ) : null}
    </div>
  )
}
