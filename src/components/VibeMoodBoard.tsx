import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useMotionProfile } from '../motion/useMotionProfile'
import { easeOut } from '../motion/tokens'

export const VIBE_PHOTOS = [
  { src: '/vibe/santorini.png', label: 'Санторини' },
  { src: '/vibe/maldives.jpg', label: 'Мальдивы' },
  { src: '/vibe/coast.jpg', label: 'Побережье' },
  { src: '/vibe/sunset-resort.jpg', label: 'Закат' },
  { src: '/vibe/evening-beach.jpg', label: 'Пляж' },
  { src: '/vibe/night-pool.jpg', label: 'Вечер' },
  { src: '/vibe/elephants.jpg', label: 'Джунгли' },
] as const

type VibeMoodBoardProps = {
  activeStep?: number
  className?: string
}

export function VibeMoodBoard({ activeStep = 0, className = '' }: VibeMoodBoardProps) {
  const profile = useMotionProfile()
  const reduce = profile.reduce
  const [focus, setFocus] = useState(0)

  useEffect(() => {
    if (reduce) return
    const id = window.setInterval(() => {
      setFocus((i) => (i + 1) % VIBE_PHOTOS.length)
    }, 3800)
    return () => window.clearInterval(id)
  }, [reduce])

  // Soft nudge when analysis advances — calm, one step only
  useEffect(() => {
    if (reduce || activeStep <= 0) return
    setFocus((i) => (i + 1) % VIBE_PHOTOS.length)
  }, [activeStep, reduce])

  const heroIndex = focus % VIBE_PHOTOS.length
  const hero = VIBE_PHOTOS[heroIndex]

  return (
    <div className={`relative overflow-hidden rounded-[28px] bg-surface-muted ${className}`}>
      <div className="relative aspect-[5/4] w-full sm:aspect-[4/3]" aria-label="Галерея отдыха">
        {VIBE_PHOTOS.map((photo, i) => (
          <motion.img
            key={photo.src}
            src={photo.src}
            alt=""
            aria-hidden={i !== heroIndex}
            className="absolute inset-0 h-full w-full object-cover"
            initial={false}
            animate={{
              opacity: i === heroIndex ? 1 : 0,
              scale: i === heroIndex ? 1 : 1.04,
            }}
            transition={{
              duration: reduce ? 0 : 1.25,
              ease: easeOut,
            }}
            draggable={false}
          />
        ))}

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/45 via-black/5 to-transparent" />

        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 px-4 pb-4 pr-[5.5rem] sm:px-5 sm:pb-5 sm:pr-28">
          <motion.p
            key={hero.label}
            className="text-[13px] font-medium tracking-wide text-white/90"
            initial={reduce ? false : { opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: easeOut }}
          >
            {hero.label}
          </motion.p>
          <div className="flex items-center gap-1.5" aria-hidden>
            {VIBE_PHOTOS.map((photo, i) => (
              <span
                key={photo.src}
                className={`h-1 rounded-full transition-all duration-500 ${
                  i === heroIndex ? 'w-4 bg-white' : 'w-1 bg-white/40'
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
