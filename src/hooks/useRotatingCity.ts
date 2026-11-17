import { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { SHORT_CITIES } from '../data/topCities'

const ROTATE_MS = 1600

/** Shared rotation index so hero title and boarding-strip destination stay in sync. */
export function useRotatingCityIndex() {
  const reduce = useReducedMotion()
  const [index, setIndex] = useState(0)

  useEffect(() => {
    if (reduce) return
    const id = window.setInterval(() => {
      setIndex((current) => (current + 1) % SHORT_CITIES.length)
    }, ROTATE_MS)
    return () => window.clearInterval(id)
  }, [reduce])

  return reduce ? 0 : index
}
