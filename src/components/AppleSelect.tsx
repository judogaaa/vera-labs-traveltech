import { useEffect, useId, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

export type AppleSelectOption<T extends string = string> = {
  value: T
  label: string
}

export function AppleSelect<T extends string>({
  value,
  options,
  onChange,
  label,
  className = '',
}: {
  value: T
  options: AppleSelectOption<T>[]
  onChange: (value: T) => void
  label?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  const profile = useMotionProfile()
  const reduce = profile.reduce
  const current = options.find((o) => o.value === value)?.label ?? value

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
    <div ref={rootRef} className={`relative ${className}`}>
      {label ? <span className="sr-only">{label}</span> : null}
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
        className={`flex h-12 w-full items-center justify-between gap-2 rounded-2xl border bg-white px-3 text-left text-sm font-semibold text-[#1c1c1e] transition-colors ${
          open ? 'border-[#007aff]' : 'border-border hover:border-border-strong'
        }`}
      >
        <span className="min-w-0 truncate">{current}</span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-[#8e8e93] transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>

      <AnimatePresence>
        {open ? (
          <motion.ul
            id={listId}
            role="listbox"
            aria-label={label || 'Варианты'}
            initial={reduce ? false : { opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? undefined : { opacity: 0, y: 4, scale: 0.98 }}
            transition={reduce ? { duration: 0.12 } : springs.snappy}
            className="absolute left-0 right-0 z-40 mt-2 max-h-64 overflow-auto rounded-[14px] border border-black/5 bg-white/95 py-1.5 shadow-[0_12px_40px_rgba(0,0,0,0.14),0_2px_8px_rgba(0,0,0,0.06)] backdrop-blur-xl"
          >
            {options.map((option) => {
              const selected = option.value === value
              return (
                <li key={option.value} role="option" aria-selected={selected}>
                  <button
                    type="button"
                    className={`flex h-11 w-full items-center justify-between gap-3 px-3.5 text-left text-[15px] transition-colors ${
                      selected
                        ? 'bg-[#007aff]/[0.08] font-semibold text-[#007aff]'
                        : 'font-medium text-[#1c1c1e] hover:bg-black/[0.04]'
                    }`}
                    onClick={() => {
                      onChange(option.value)
                      setOpen(false)
                    }}
                  >
                    <span className="min-w-0 truncate">{option.label}</span>
                    {selected ? <Check size={16} className="shrink-0 text-[#007aff]" aria-hidden /> : null}
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
