import { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import type { MotionProfile } from './tokens'

function readCoarse(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(pointer: coarse)').matches || window.matchMedia('(hover: none)').matches
}

function readCompact(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(max-width: 767px)').matches
}

/** Shared motion profile: reduced-motion + device class (touch / compact). */
export function useMotionProfile(): MotionProfile {
  const reduce = Boolean(useReducedMotion())
  const [coarse, setCoarse] = useState(readCoarse)
  const [compact, setCompact] = useState(readCompact)

  useEffect(() => {
    const coarseMq = window.matchMedia('(pointer: coarse)')
    const hoverMq = window.matchMedia('(hover: none)')
    const compactMq = window.matchMedia('(max-width: 767px)')
    const sync = () => {
      setCoarse(coarseMq.matches || hoverMq.matches)
      setCompact(compactMq.matches)
    }
    sync()
    coarseMq.addEventListener('change', sync)
    hoverMq.addEventListener('change', sync)
    compactMq.addEventListener('change', sync)
    return () => {
      coarseMq.removeEventListener('change', sync)
      hoverMq.removeEventListener('change', sync)
      compactMq.removeEventListener('change', sync)
    }
  }, [])

  return { reduce, coarse, compact }
}
