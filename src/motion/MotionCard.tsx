import { motion } from 'framer-motion'
import type { HTMLAttributes, ReactNode } from 'react'
import { useMotionProfile } from './useMotionProfile'
import { cardHover, cardTap, enterAnimate, enterInitial, enterTransition, listItemVariants } from './tokens'

type Props = {
  children: ReactNode
  className?: string
  layoutId?: string
  /** Stagger index inside a list (optional). */
  index?: number
  onClick?: HTMLAttributes<HTMLElement>['onClick']
  onKeyDown?: HTMLAttributes<HTMLElement>['onKeyDown']
  role?: HTMLAttributes<HTMLElement>['role']
  tabIndex?: number
  'aria-label'?: string
}

/** Interactive surface: hover lift on desktop, tap press on touch, soft enter. */
export function MotionCard({
  children,
  className = '',
  layoutId,
  index = 0,
  onClick,
  onKeyDown,
  role,
  tabIndex,
  'aria-label': ariaLabel,
}: Props) {
  const profile = useMotionProfile()
  const delay = profile.reduce ? 0 : Math.min(index, 8) * 0.03

  return (
    <motion.article
      layoutId={layoutId}
      className={className}
      role={role}
      tabIndex={tabIndex}
      aria-label={ariaLabel}
      onClick={onClick}
      onKeyDown={onKeyDown}
      initial={enterInitial(profile)}
      animate={enterAnimate(profile)}
      transition={enterTransition(profile, delay)}
      whileHover={cardHover(profile)}
      whileTap={cardTap(profile)}
      variants={listItemVariants(profile)}
    >
      {children}
    </motion.article>
  )
}
