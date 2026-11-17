import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { enterAnimate, enterInitial, enterTransition } from '../motion/tokens'
import { useMotionProfile } from '../motion/useMotionProfile'

export function PageEnter({
  children,
  className = '',
  delay = 0,
}: {
  children: ReactNode
  className?: string
  delay?: number
}) {
  const profile = useMotionProfile()
  return (
    <motion.div
      className={className || undefined}
      initial={enterInitial(profile)}
      animate={enterAnimate(profile)}
      transition={enterTransition(profile, delay)}
    >
      {children}
    </motion.div>
  )
}
