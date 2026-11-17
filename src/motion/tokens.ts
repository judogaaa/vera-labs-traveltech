import type { Transition, Variants } from 'framer-motion'

/** Apple-like springs — snappy UI chrome, softer page content. */
export const springs = {
  snappy: { type: 'spring', stiffness: 520, damping: 40, mass: 0.85 } satisfies Transition,
  soft: { type: 'spring', stiffness: 280, damping: 34, mass: 1 } satisfies Transition,
  gentle: { type: 'spring', stiffness: 200, damping: 30, mass: 1 } satisfies Transition,
  sheet: { type: 'spring', stiffness: 420, damping: 38, mass: 0.9 } satisfies Transition,
  tap: { type: 'spring', stiffness: 600, damping: 32, mass: 0.7 } satisfies Transition,
} as const

export const durations = {
  instant: 0.12,
  fast: 0.18,
  normal: 0.28,
  slow: 0.4,
} as const

export const easeOut = [0.22, 1, 0.36, 1] as const

export type MotionProfile = {
  reduce: boolean
  /** Touch / coarse pointer — prefer tap feedback over hover. */
  coarse: boolean
  /** Narrow viewport — iOS-like push, bottom sheets. */
  compact: boolean
}

export function pageTransition(profile: MotionProfile): Transition {
  if (profile.reduce) return { duration: durations.instant, ease: 'easeOut' }
  if (profile.compact) return { ...springs.snappy }
  return { ...springs.soft }
}

export function pageVariants(profile: MotionProfile): Variants {
  if (profile.reduce) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    }
  }
  if (profile.compact) {
    // iOS-like push: slight lateral move + fade
    return {
      initial: { opacity: 0, x: 18, scale: 0.992 },
      animate: { opacity: 1, x: 0, scale: 1 },
      exit: { opacity: 0, x: -10, scale: 0.995 },
    }
  }
  // Desktop Apple-site: soft rise
  return {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -6 },
  }
}

export function enterTransition(profile: MotionProfile, delay = 0): Transition {
  if (profile.reduce) return { duration: durations.instant, delay, ease: 'easeOut' }
  return { ...springs.gentle, delay }
}

export function enterInitial(profile: MotionProfile) {
  if (profile.reduce) return { opacity: 0 }
  return { opacity: 0, y: profile.compact ? 8 : 12 }
}

export function enterAnimate(_profile: MotionProfile) {
  return { opacity: 1, y: 0 }
}

export function modalBackdropTransition(profile: MotionProfile): Transition {
  return { duration: profile.reduce ? durations.instant : durations.fast, ease: 'easeOut' }
}

export function modalPanelTransition(profile: MotionProfile): Transition {
  if (profile.reduce) return { duration: durations.instant, ease: 'easeOut' }
  return profile.compact ? { ...springs.sheet } : { ...springs.soft }
}

export function modalPanelInitial(profile: MotionProfile) {
  if (profile.reduce) return { opacity: 0 }
  if (profile.compact) return { opacity: 0.96, y: '100%' }
  return { opacity: 0, y: 16, scale: 0.98 }
}

export function modalPanelAnimate(_profile: MotionProfile) {
  return { opacity: 1, y: 0, scale: 1 }
}

export function modalPanelExit(profile: MotionProfile) {
  if (profile.reduce) return { opacity: 0 }
  if (profile.compact) return { opacity: 0.98, y: '40%' }
  return { opacity: 0, y: 8, scale: 0.98 }
}

export function cardHover(profile: MotionProfile) {
  if (profile.reduce || profile.coarse) return undefined
  return { y: -3, transition: springs.snappy }
}

export function cardTap(profile: MotionProfile) {
  if (profile.reduce) return undefined
  return { scale: 0.985, transition: springs.tap }
}

export function staggerChildren(profile: MotionProfile, step = 0.035) {
  if (profile.reduce) return { staggerChildren: 0, delayChildren: 0 }
  return { staggerChildren: step, delayChildren: 0.04 }
}

export function listItemVariants(profile: MotionProfile): Variants {
  if (profile.reduce) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
    }
  }
  return {
    initial: { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0 },
  }
}
