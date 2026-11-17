import { useEffect, useRef, useState } from 'react'
import { Button } from '../Button'
import type { TripProgressStep } from '../../types/trip'

type Message = { role: 'user' | 'assistant' | 'system'; content: string }

type Props = {
  messages: Message[]
  busy: boolean
  progress: TripProgressStep | null
  suggestions: string[]
  placeholder?: string
  onSend: (text: string) => void
}

export function TripChat({ messages, busy, progress, suggestions, placeholder, onSend }: Props) {
  const [text, setText] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, progress])

  const submit = () => {
    const value = text.trim()
    if (!value || busy) return
    setText('')
    onSend(value)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-1 py-2">
        {messages.map((m, i) => (
          <div
            key={`${m.role}-${i}`}
            className={`max-w-[92%] rounded-2xl px-3.5 py-2.5 text-[14px] leading-5 ${
              m.role === 'user'
                ? 'ml-auto bg-brand-blue-900 text-white'
                : m.role === 'system'
                  ? 'bg-brand-green-100 text-brand-blue-950'
                  : 'bg-white text-text-primary border border-border'
            }`}
          >
            {m.content}
          </div>
        ))}
        {busy && progress ? (
          <div className="rounded-2xl border border-border bg-surface-soft px-3.5 py-2.5 text-[14px] text-text-secondary">
            <span className="inline-flex items-center gap-2">
              <span className="oh-pulse h-2 w-2 rounded-full bg-brand-green-500" />
              {progress}…
            </span>
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      {!busy && suggestions.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSend(s)}
              className="rounded-full border border-border bg-white px-3 py-1.5 text-xs font-semibold text-brand-blue-900 hover:border-brand-green-400 hover:bg-brand-green-100"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex gap-2 border-t border-border pt-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          rows={2}
          placeholder={placeholder || 'Напишите, куда и на сколько дней…'}
          className="min-h-[48px] flex-1 resize-none rounded-2xl border border-border bg-white px-3 py-2.5 text-[14px] outline-none focus:border-brand-blue-700"
          disabled={busy}
        />
        <Button onClick={submit} disabled={busy || !text.trim()} className="self-end">
          Отправить
        </Button>
      </div>
    </div>
  )
}
