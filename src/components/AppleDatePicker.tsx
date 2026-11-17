import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function toIso(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function parseIso(iso: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) return null
  return dt
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

function formatField(iso: string): string {
  const d = parseIso(iso)
  if (!d) return 'Выберите дату'
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }).replace('.', '')
}

function monthTitle(d: Date): string {
  const raw = d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
  return raw.charAt(0).toUpperCase() + raw.slice(1)
}

function buildGrid(view: Date): { date: Date; inMonth: boolean }[] {
  const first = new Date(view.getFullYear(), view.getMonth(), 1)
  // Monday-first: JS Sunday=0 → shift so Monday=0
  const weekday = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(first.getDate() - weekday)
  const cells: { date: Date; inMonth: boolean }[] = []
  for (let i = 0; i < 42; i++) {
    const date = new Date(start)
    date.setDate(start.getDate() + i)
    cells.push({ date, inMonth: date.getMonth() === view.getMonth() })
  }
  return cells
}

export function AppleDatePicker({
  label,
  value,
  min,
  max,
  onChange,
  align = 'start',
}: {
  label: string
  value: string
  min?: string
  max?: string
  onChange: (iso: string) => void
  align?: 'start' | 'end'
}) {
  const [open, setOpen] = useState(false)
  const selected = parseIso(value)
  const [view, setView] = useState(() => selected ?? new Date())
  const rootRef = useRef<HTMLDivElement>(null)
  const panelId = useId()
  const profile = useMotionProfile()
  const reduce = profile.reduce
  const todayIso = toIso(new Date())
  const minDate = min ? parseIso(min) : null
  const maxDate = max ? parseIso(max) : null

  useEffect(() => {
    if (!open) return
    const base = parseIso(value)
    if (base) setView(new Date(base.getFullYear(), base.getMonth(), 1))
  }, [open, value])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('mousedown', onDoc)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDoc)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const cells = useMemo(() => buildGrid(view), [view])

  const isDisabled = (d: Date) => {
    const day = startOfDay(d)
    if (minDate && day < startOfDay(minDate)) return true
    if (maxDate && day > startOfDay(maxDate)) return true
    return false
  }

  const pick = (d: Date) => {
    if (isDisabled(d)) return
    onChange(toIso(d))
    setOpen(false)
  }

  const goToday = () => {
    const t = startOfDay(new Date())
    if (isDisabled(t)) return
    onChange(toIso(t))
    setView(new Date(t.getFullYear(), t.getMonth(), 1))
    setOpen(false)
  }

  const clear = () => {
    // Keep a valid ISO for booking flow — jump to min or today.
    const fallback = minDate ?? startOfDay(new Date())
    onChange(toIso(fallback))
    setOpen(false)
  }

  return (
    <div ref={rootRef} className="relative block text-sm font-medium text-text-primary">
      <span className="block">{label}</span>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className={`mt-1.5 flex h-11 w-full items-center justify-between gap-2 rounded-2xl border bg-white px-3 text-left text-[15px] font-normal transition-colors ${
          open ? 'border-[#007aff] ring-2 ring-[#007aff]/20' : 'border-border hover:border-border-strong'
        }`}
      >
        <span className={selected ? 'text-[#1c1c1e]' : 'text-[#8e8e93]'}>{formatField(value)}</span>
        <CalendarDays className="h-4 w-4 shrink-0 text-[#8e8e93]" strokeWidth={1.75} aria-hidden />
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            id={panelId}
            role="dialog"
            aria-label={label}
            initial={reduce ? false : { opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? undefined : { opacity: 0, y: 4, scale: 0.98 }}
            transition={reduce ? { duration: 0.12 } : springs.snappy}
            className={`apple-date-panel absolute top-[calc(100%+8px)] z-40 w-[280px] overflow-hidden rounded-[18px] border border-black/5 bg-white/95 p-3 shadow-[0_12px_40px_rgba(0,0,0,0.14),0_2px_8px_rgba(0,0,0,0.06)] backdrop-blur-xl ${
              align === 'end' ? 'right-0' : 'left-0'
            }`}
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <p className="text-[15px] font-semibold tracking-[-0.01em] text-[#1c1c1e]">
                {monthTitle(view)}
              </p>
              <div className="flex items-center gap-0.5">
                <button
                  type="button"
                  aria-label="Предыдущий месяц"
                  onClick={() => setView(new Date(view.getFullYear(), view.getMonth() - 1, 1))}
                  className="flex h-8 w-8 items-center justify-center rounded-full text-[#007aff] transition-colors hover:bg-black/[0.04]"
                >
                  <ChevronLeft className="h-4 w-4" strokeWidth={2.25} />
                </button>
                <button
                  type="button"
                  aria-label="Следующий месяц"
                  onClick={() => setView(new Date(view.getFullYear(), view.getMonth() + 1, 1))}
                  className="flex h-8 w-8 items-center justify-center rounded-full text-[#007aff] transition-colors hover:bg-black/[0.04]"
                >
                  <ChevronRight className="h-4 w-4" strokeWidth={2.25} />
                </button>
              </div>
            </div>

            <div className="mb-1 grid grid-cols-7 gap-0">
              {WEEKDAYS.map((d) => (
                <div
                  key={d}
                  className="flex h-8 items-center justify-center text-[11px] font-semibold uppercase tracking-wide text-[#8e8e93]"
                >
                  {d}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-7 gap-0">
              {cells.map(({ date, inMonth }) => {
                const iso = toIso(date)
                const selectedDay = value === iso
                const isToday = iso === todayIso
                const disabled = isDisabled(date)
                return (
                  <button
                    key={iso + String(inMonth)}
                    type="button"
                    disabled={disabled}
                    onClick={() => pick(date)}
                    className={`relative flex h-9 items-center justify-center text-[15px] transition-colors ${
                      disabled ? 'cursor-not-allowed opacity-30' : 'hover:bg-black/[0.04]'
                    } ${inMonth ? 'text-[#1c1c1e]' : 'text-[#c7c7cc]'} rounded-full`}
                  >
                    <span
                      className={`flex h-8 w-8 items-center justify-center rounded-full ${
                        selectedDay
                          ? 'bg-[#007aff] font-semibold text-white shadow-[0_1px_2px_rgba(0,122,255,0.35)]'
                          : isToday && !selectedDay
                            ? 'font-semibold text-[#007aff]'
                            : ''
                      }`}
                    >
                      {date.getDate()}
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="mt-2 flex items-center justify-between border-t border-black/[0.06] px-1 pt-2">
              <button
                type="button"
                onClick={clear}
                className="text-[15px] font-medium text-[#007aff] transition-opacity hover:opacity-70"
              >
                Удалить
              </button>
              <button
                type="button"
                onClick={goToday}
                className="text-[15px] font-medium text-[#007aff] transition-opacity hover:opacity-70"
              >
                Сегодня
              </button>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
