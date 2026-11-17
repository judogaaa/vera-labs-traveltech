import { useEffect } from 'react'
import { X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { IconButton } from './IconButton'
import { useMotionProfile } from '../motion/useMotionProfile'
import {
  modalBackdropTransition,
  modalPanelAnimate,
  modalPanelExit,
  modalPanelInitial,
  modalPanelTransition,
} from '../motion/tokens'

export function Modal({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
}) {
  const profile = useMotionProfile()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = prev
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4"
          role="dialog"
          aria-modal="true"
          aria-label={title}
        >
          <motion.button
            type="button"
            className="absolute inset-0 bg-black/35 backdrop-blur-[2px]"
            aria-label="Закрыть"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={modalBackdropTransition(profile)}
          />
          <motion.div
            className={`relative z-10 w-full max-w-lg border border-border-default bg-white p-5 shadow-[0_16px_48px_rgba(14,23,77,0.12)] sm:rounded-[24px] sm:p-6 ${
              profile.compact ? 'rounded-t-[24px] pb-[max(1.25rem,env(safe-area-inset-bottom))]' : ''
            }`}
            initial={modalPanelInitial(profile)}
            animate={modalPanelAnimate(profile)}
            exit={modalPanelExit(profile)}
            transition={modalPanelTransition(profile)}
          >
            <div className="mb-4 flex items-start justify-between gap-3">
              <h2 className="text-xl font-bold text-brand-blue-950">{title}</h2>
              <IconButton label="Закрыть" onClick={onClose}>
                <X size={18} />
              </IconButton>
            </div>
            <div className="text-[15px] leading-6 text-text-secondary">{children}</div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  )
}
