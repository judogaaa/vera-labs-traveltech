import { claimStatusLabel, attributeLabel } from '../labels'
import type { ClaimStatus } from '../types'

type Props = {
  attributeKey: string
  status?: ClaimStatus | string
  tone?: 'matched' | 'unmatched' | 'unknown' | 'neutral'
  valueHint?: string
}

const toneClass: Record<NonNullable<Props['tone']>, string> = {
  matched: 'border-brand-green-400/60 bg-brand-green-100 text-brand-blue-950',
  unmatched: 'border-border bg-surface-soft text-text-secondary',
  unknown: 'border-dashed border-border bg-white text-text-muted',
  neutral: 'border-border bg-white text-brand-blue-950',
}

export function AttributeBadge({
  attributeKey,
  status,
  tone = 'neutral',
  valueHint,
}: Props) {
  const label = attributeLabel(attributeKey)
  const statusText = status ? claimStatusLabel(status) : null
  return (
    <span
      className={`inline-flex max-w-full flex-wrap items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${toneClass[tone]}`}
      title={[label, statusText, valueHint].filter(Boolean).join(' · ')}
    >
      <span className="truncate">{label}</span>
      {statusText ? (
        <span className="rounded-full bg-white/70 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">
          {statusText}
        </span>
      ) : null}
      {valueHint ? <span className="truncate text-text-secondary">{valueHint}</span> : null}
    </span>
  )
}
