import { attributeLabel, claimStatusLabel, formatObservationValue, scopeLabel } from '../labels'
import type { AttributeObservation } from '../types'

type Props = {
  observations: AttributeObservation[]
  emptyMessage?: string
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function EvidenceList({
  observations,
  emptyMessage = 'Пока нет наблюдений с источниками.',
}: Props) {
  if (!observations.length) {
    return (
      <p className="rounded-2xl border border-dashed border-border bg-surface-soft p-4 text-sm text-text-secondary">
        {emptyMessage}
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-3" aria-label="Источники и доказательства">
      {observations.map((obs) => (
        <li
          key={obs.observation_id}
          className="rounded-2xl border border-border bg-white p-4 shadow-sm"
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-sm font-bold text-brand-blue-950">
                {attributeLabel(obs.attribute_key)}
              </p>
              <p className="mt-1 text-xs text-text-muted">
                Область: {scopeLabel(obs.scope.kind)}
                {obs.scope.identifier ? ` · ${obs.scope.identifier}` : ''}
              </p>
            </div>
            <span className="rounded-full border border-border bg-surface-soft px-2.5 py-1 text-[11px] font-semibold text-brand-blue-950">
              {claimStatusLabel(obs.status)}
            </span>
          </div>

          <p className="mt-3 text-sm text-text-primary">
            {formatObservationValue(obs.attribute_key, obs.value)}
            {obs.confidence != null ? (
              <span className="ml-2 text-xs text-text-muted">
                уверенность {(obs.confidence * 100).toFixed(0)}%
              </span>
            ) : null}
          </p>

          <dl className="mt-3 grid gap-1 text-xs text-text-secondary sm:grid-cols-2">
            <div>
              <dt className="inline font-medium text-text-muted">Метод: </dt>
              <dd className="inline">
                {obs.method} ({obs.method_version})
              </dd>
            </div>
            <div>
              <dt className="inline font-medium text-text-muted">Наблюдено: </dt>
              <dd className="inline">{formatDate(obs.observed_at)}</dd>
            </div>
            {obs.valid_until ? (
              <div>
                <dt className="inline font-medium text-text-muted">Действует до: </dt>
                <dd className="inline">{formatDate(obs.valid_until)}</dd>
              </div>
            ) : null}
          </dl>

          {obs.sources?.length ? (
            <ul className="mt-3 flex flex-col gap-1.5 border-t border-border pt-3">
              {obs.sources.map((src, i) => (
                <li key={`${obs.observation_id}-${i}`} className="text-xs text-text-secondary">
                  <span className="font-semibold text-brand-blue-950">{src.kind}</span>
                  {src.kind === 'hotelier_simulated' ? (
                    <span className="ml-1 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                      симуляция
                    </span>
                  ) : null}
                  {' · '}
                  <a
                    href={src.uri.startsWith('http') ? src.uri : undefined}
                    className="break-all text-brand-blue-800 underline-offset-2 hover:underline"
                    target="_blank"
                    rel="noreferrer"
                  >
                    {src.uri}
                  </a>
                  <span className="text-text-muted"> · {formatDate(src.fetched_at)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-xs text-text-muted">Источники не указаны (статус: {obs.status}).</p>
          )}
        </li>
      ))}
    </ul>
  )
}
