import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, MessageSquareText } from 'lucide-react'
import {
  answerHotelierQuestion,
  fetchConflicts,
  fetchHotelierQuestions,
} from '../features/hotelIntelligence/api'
import type {
  ConflictRecord,
  HotelierQuestion,
  HotelIntelligenceApiError,
} from '../features/hotelIntelligence/types'
import { attributeLabel } from '../features/hotelIntelligence/labels'
import { HotelierInbox } from '../features/hotelIntelligence/components/HotelierInbox'

function isApiError(err: unknown): err is HotelIntelligenceApiError {
  return Boolean(err && typeof err === 'object' && 'code' in err && 'message' in err)
}

export function HotelierCabinetScreen() {
  const [questions, setQuestions] = useState<HotelierQuestion[]>([])
  const [conflicts, setConflicts] = useState<ConflictRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')

  const reload = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    setError(null)
    try {
      const [qs, cs] = await Promise.all([
        fetchHotelierQuestions({
          status: statusFilter || undefined,
          signal,
        }),
        fetchConflicts({ signal }),
      ])
      if (signal?.aborted) return
      setQuestions(qs)
      setConflicts(cs)
    } catch (err) {
      if (signal?.aborted) return
      setError(
        isApiError(err)
          ? err.message
          : 'Не удалось загрузить кабинет отельера',
      )
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    const ac = new AbortController()
    void reload(ac.signal)
    return () => ac.abort()
  }, [reload])

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
          <MessageSquareText size={17} aria-hidden />
          Кабинет отельера
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-brand-blue-950 sm:text-4xl">
          Вопросы, ответы и конфликты
        </h1>
        <p className="mt-3 text-sm leading-6 text-text-secondary sm:text-base">
          Демо-режим: ответы сохраняются как <strong>симуляция</strong> и не могут сами по себе
          выставить статус verified. Сырой текст, извлечённые поля и история видны ниже.
        </p>
      </header>

      <div className="mt-6 flex flex-wrap gap-2" role="group" aria-label="Фильтр статуса">
        {[
          { id: '', label: 'Все' },
          { id: 'open', label: 'Открытые' },
          { id: 'answered', label: 'Отвеченные' },
        ].map((opt) => (
          <button
            key={opt.id || 'all'}
            type="button"
            aria-pressed={statusFilter === opt.id}
            onClick={() => setStatusFilter(opt.id)}
            className={[
              'rounded-full border px-3 py-1.5 text-xs font-semibold',
              statusFilter === opt.id
                ? 'border-brand-blue-800 bg-brand-blue-950 text-white'
                : 'border-border bg-white text-text-secondary',
            ].join(' ')}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {error ? (
        <div className="mt-6 rounded-2xl border border-border bg-error-bg/30 p-5" role="alert">
          <p className="text-sm font-semibold text-error">{error}</p>
          <button
            type="button"
            className="mt-3 rounded-full border border-border bg-white px-4 py-2 text-sm font-semibold"
            onClick={() => void reload()}
          >
            Повторить
          </button>
        </div>
      ) : null}

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1.2fr)_minmax(260px,0.8fr)]">
        <section aria-labelledby="inbox-title">
          <h2 id="inbox-title" className="mb-4 text-xl font-bold text-brand-blue-950">
            Входящие
          </h2>
          <HotelierInbox
            questions={questions}
            loading={loading}
            onAnswer={async (questionId, rawText) => {
              // Demo cabinet cannot claim official hotelier authority.
              const res = await answerHotelierQuestion(questionId, rawText, {
                simulated: true,
              })
              await reload()
              return res.observations
            }}
          />
        </section>

        <aside className="space-y-6">
          <section
            className="rounded-[22px] border border-border bg-white p-5 shadow-sm"
            aria-labelledby="sim-note"
          >
            <h2 id="sim-note" className="text-sm font-bold text-brand-blue-950">
              Пометка симуляции
            </h2>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              Все ответы из этого кабинета уходят с флагом <code className="text-xs">simulated:
              true</code>. Источник наблюдения — <code className="text-xs">hotelier_simulated</code>.
              Для продакшена нужен реальный канал отельера.
            </p>
          </section>

          <section aria-labelledby="conflict-side">
            <h2 id="conflict-side" className="mb-3 text-lg font-bold text-brand-blue-950">
              Конфликты
            </h2>
            {!conflicts.length ? (
              <p className="text-sm text-text-secondary">Конфликтов нет.</p>
            ) : (
              <ul className="space-y-2">
                {conflicts.map((c) => (
                  <li
                    key={c.conflict_id}
                    className="rounded-xl border border-border bg-surface-soft p-3 text-sm"
                  >
                    <p className="font-semibold text-brand-blue-950">
                      {attributeLabel(c.attribute_key)} · {c.status}
                    </p>
                    <p className="mt-1 text-xs text-text-secondary">{c.hotel_id}</p>
                    <p className="mt-1 text-xs text-text-muted">{c.reason}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </main>
  )
}
