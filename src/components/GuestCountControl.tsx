import { useEffect, useId, useRef, useState } from 'react'
import { Check, ChevronDown, Minus, Plus } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

const OPTIONS = [
  { value: 1, label: '1 гость' },
  { value: 2, label: '2 гостя' },
  { value: 3, label: '3 гостя' },
  { value: 4, label: '4 гостя' },
]

export function GuestCountControl({
  value,
  onChange,
}: {
  value: number
  onChange: (value: number) => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  const profile = useMotionProfile()
  const reduce = profile.reduce

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

  return (
    <div ref={rootRef} className="relative">
      <p className="mb-1.5 text-sm font-medium text-text-primary">Гости</p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Меньше гостей"
          disabled={value <= 1}
          onClick={() => onChange(Math.max(1, value - 1))}
          className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-border bg-white text-brand-blue-950 transition-colors hover:border-brand-green-400 hover:bg-brand-green-100 disabled:opacity-40"
        >
          <Minus size={16} aria-hidden />
        </button>
        <button
          type="button"
          className="flex h-11 min-w-0 flex-1 items-center justify-between rounded-2xl border border-[#E3E5EA] bg-white px-3 text-left text-sm font-semibold text-brand-blue-950 transition-colors hover:border-brand-green-400 hover:bg-brand-green-100"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen((v) => !v)}
        >
          <span>
            Гости · {value}
          </span>
          <ChevronDown size={16} className={`transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
        </button>
        <button
          type="button"
          aria-label="Больше гостей"
          disabled={value >= 4}
          onClick={() => onChange(Math.min(4, value + 1))}
          className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-border bg-white text-brand-blue-950 transition-colors hover:border-brand-green-400 hover:bg-brand-green-100 disabled:opacity-40"
        >
          <Plus size={16} aria-hidden />
        </button>
      </div>

      <AnimatePresence>
        {open ? (
          <motion.ul
            id={listId}
            role="listbox"
            aria-label="Количество гостей"
            className="absolute left-0 right-0 z-30 mt-2 overflow-hidden rounded-2xl border border-[#E3E5EA] bg-white py-1 shadow-[0_12px_32px_rgba(14,23,77,0.1)]"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: 4, scale: 0.98 }}
            transition={reduce ? { duration: 0.12 } : springs.snappy}
          >
            {OPTIONS.map((option) => {
              const selected = option.value === value
              return (
                <li key={option.value} role="option" aria-selected={selected}>
                  <button
                    type="button"
                    className={`flex h-12 w-full items-center justify-between px-4 text-left text-sm font-medium transition-colors ${
                      selected
                        ? 'bg-brand-green-100 text-brand-blue-950'
                        : 'text-text-primary hover:bg-brand-green-100'
                    }`}
                    onClick={() => {
                      onChange(option.value)
                      setOpen(false)
                    }}
                  >
                    {option.label}
                    {selected ? <Check size={16} className="text-brand-blue-950" aria-hidden /> : null}
                  </button>
                </li>
              )
            })}
          </motion.ul>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
