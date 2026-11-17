import { useState } from 'react'
import { attributeLabel, claimStatusLabel, formatObservationValue, scopeLabel } from '../labels'
import type { AttributeObservation, HotelierQuestion } from '../types'

type Props = {
  questions: HotelierQuestion[]
  loading?: boolean
  onAnswer: (
    questionId: string,
    rawText: string,
  ) => Promise<AttributeObservation[] | void>
}

export function HotelierInbox({ questions, loading, onAnswer }: Props) {
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [busyId, setBusyId] = useState<string | null>(null)
  const [lastExtracted, setLastExtracted] = useState<
    Record<string, AttributeObservation[]>
  >({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  if (loading) {
    return (
      <div className="space-y-3" aria-busy="true">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-2xl border border-border bg-surface-soft"
          />
        ))}
      </div>
    )
  }

  if (!questions.length) {
    return (
      <p className="rounded-2xl border border-dashed border-border bg-surface-soft p-5 text-sm text-text-secondary">
        Вопросов отельеру пока нет. Они появляются после enrichment, когда нужен ответ по
        номеру (например, blackout).
      </p>
    )
  }

  return (
    <ul className="flex flex-col gap-4" aria-label="Входящие вопросы отельеру">
      {questions.map((q) => {
        const draft = drafts[q.question_id] ?? ''
        const extracted = lastExtracted[q.question_id]
        return (
          <li
            key={q.question_id}
            className="rounded-[22px] border border-border bg-white p-4 shadow-sm sm:p-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-blue-800">
                  {attributeLabel(q.attribute_key)} · {q.hotel_id}
                </p>
                <h3 className="mt-1 text-base font-bold text-brand-blue-950">{q.question_text}</h3>
                {q.scope ? (
                  <p className="mt-1 text-xs text-text-muted">
                    Область: {scopeLabel(q.scope.kind)}
                    {q.scope.identifier ? ` · ${q.scope.identifier}` : ''}
                  </p>
                ) : null}
              </div>
              <span className="rounded-full border border-border bg-surface-soft px-2.5 py-1 text-[11px] font-semibold text-brand-blue-950">
                {q.status}
              </span>
            </div>

            {q.answers?.length ? (
              <div className="mt-4 space-y-2 border-t border-border pt-3">
                <p className="text-xs font-semibold text-brand-blue-950">История ответов</p>
                {q.answers.map((a) => (
                  <div
                    key={a.answer_id}
                    className="rounded-xl bg-surface-soft p-3 text-sm text-text-secondary"
                  >
                    <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
                      <span className="font-semibold text-brand-blue-950">{a.source_kind}</span>
                      {a.source_kind === 'hotelier_simulated' ? (
                        <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
                          симуляция — не verified
                        </span>
                      ) : null}
                      <span className="text-text-muted">{a.created_at}</span>
                    </div>
                    <p className="whitespace-pre-wrap">{a.raw_text}</p>
                    {a.extraction && Object.keys(a.extraction).length > 0 ? (
                      <pre className="mt-2 overflow-x-auto rounded-lg bg-white p-2 text-[11px] text-text-muted">
                        {JSON.stringify(a.extraction, null, 2)}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}

            <form
              className="mt-4 space-y-3"
              onSubmit={async (e) => {
                e.preventDefault()
                if (!draft.trim() || busyId) return
                setBusyId(q.question_id)
                setErrors((prev) => ({ ...prev, [q.question_id]: '' }))
                try {
                  const obs = await onAnswer(q.question_id, draft.trim())
                  if (obs) setLastExtracted((prev) => ({ ...prev, [q.question_id]: obs }))
                  setDrafts((prev) => ({ ...prev, [q.question_id]: '' }))
                } catch (err) {
                  const message =
                    err && typeof err === 'object' && 'message' in err
                      ? String((err as { message: string }).message)
                      : 'Не удалось сохранить ответ'
                  setErrors((prev) => ({ ...prev, [q.question_id]: message }))
                } finally {
                  setBusyId(null)
                }
              }}
            >
              <label className="block text-xs font-medium text-text-secondary" htmlFor={`ans-${q.question_id}`}>
                Сырой ответ отельера (демо — всегда как симуляция)
              </label>
              <textarea
                id={`ans-${q.question_id}`}
                rows={3}
                value={draft}
                onChange={(e) =>
                  setDrafts((prev) => ({ ...prev, [q.question_id]: e.target.value }))
                }
                className="w-full resize-y rounded-2xl border border-border bg-surface-soft px-3 py-2.5 text-sm text-text-primary outline-none focus:border-brand-blue-800"
                placeholder="Например: Да, в Deluxe есть плотные шторы блэкаут"
              />
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="submit"
                  disabled={!draft.trim() || busyId === q.question_id}
                  className="inline-flex min-h-10 items-center rounded-full bg-brand-blue-950 px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busyId === q.question_id ? 'Сохраняем…' : 'Подтвердить (симуляция)'}
                </button>
                <p className="text-xs text-amber-800">
                  Симулированный ответ не может один дать статус «verified».
                </p>
              </div>
              {errors[q.question_id] ? (
                <p className="text-sm text-error" role="alert">
                  {errors[q.question_id]}
                </p>
              ) : null}
            </form>

            {extracted?.length ? (
              <div className="mt-4 rounded-xl border border-brand-green-400/40 bg-brand-green-100/50 p-3">
                <p className="text-xs font-semibold text-brand-blue-950">Извлечённые поля</p>
                <ul className="mt-2 space-y-1 text-sm text-text-secondary">
                  {extracted.map((o) => (
                    <li key={o.observation_id}>
                      {attributeLabel(o.attribute_key)}:{' '}
                      {formatObservationValue(o.attribute_key, o.value)} ·{' '}
                      {claimStatusLabel(o.status)}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}
