import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

export function Toast({
  message,
  open,
  onClose,
}: {
  message: string
  open: boolean
  onClose: () => void
}) {
  const profile = useMotionProfile()

  useEffect(() => {
    if (!open) return
    const t = window.setTimeout(onClose, 2800)
    return () => window.clearTimeout(t)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          role="status"
          className="fixed bottom-5 left-1/2 z-50 max-w-[90vw] rounded-2xl border border-border-default bg-white px-4 py-3 text-sm font-medium text-text-primary shadow-[0_8px_28px_rgba(14,23,77,0.12)]"
          initial={
            profile.reduce
              ? { opacity: 0 }
              : profile.compact
                ? { opacity: 0, y: 24, x: '-50%' }
                : { opacity: 0, y: 12, x: '-50%', scale: 0.98 }
          }
          animate={{ opacity: 1, y: 0, x: '-50%', scale: 1 }}
          exit={
            profile.reduce
              ? { opacity: 0, x: '-50%' }
              : { opacity: 0, y: 8, x: '-50%', scale: 0.98 }
          }
          transition={profile.reduce ? { duration: 0.12 } : springs.snappy}
        >
          {message}
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
