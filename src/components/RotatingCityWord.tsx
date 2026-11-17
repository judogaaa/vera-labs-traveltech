import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { SHORT_CITIES } from '../data/topCities'
import { useRotatingCityIndex } from '../hooks/useRotatingCity'

export function RotatingCityWord() {
  const reduce = useReducedMotion()
  const index = useRotatingCityIndex()
  const city = SHORT_CITIES[index]

  if (reduce) {
    return <span className="block">Найдём {SHORT_CITIES[0]}.</span>
  }

  return (
    <span className="relative block min-h-[1.15em]">
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={city}
          className="absolute inset-x-0 top-0 block text-center"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.28, ease: 'easeOut' }}
        >
          Найдём {city}.
        </motion.span>
      </AnimatePresence>
    </span>
  )
}
