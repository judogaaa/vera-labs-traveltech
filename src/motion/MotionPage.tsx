import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { useMotionProfile } from './useMotionProfile'
import { pageTransition, pageVariants } from './tokens'

/** Route-level enter/exit — keeps header fixed, animates page body only. */
export function MotionPage({ children, className = '' }: { children: ReactNode; className?: string }) {
  const profile = useMotionProfile()
  const variants = pageVariants(profile)

  return (
    <motion.div
      className={className || undefined}
      variants={variants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={pageTransition(profile)}
      style={{ willChange: profile.reduce ? undefined : 'opacity, transform' }}
    >
      {children}
    </motion.div>
  )
}
