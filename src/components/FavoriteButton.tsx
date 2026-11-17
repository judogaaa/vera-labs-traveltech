import { Heart } from 'lucide-react'
import { motion } from 'framer-motion'
import { useFlow } from '../context/FlowContext'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

export function FavoriteButton({
  hotelId,
  className = '',
}: {
  hotelId: string
  className?: string
}) {
  const { favorites, toggleFavorite, pushToast } = useFlow()
  const active = favorites.includes(hotelId)
  const profile = useMotionProfile()

  const stop = (e: React.SyntheticEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  return (
    <motion.button
      type="button"
      aria-label={active ? 'Убрать из избранного' : 'Добавить в избранное'}
      aria-pressed={active}
      onPointerDown={stop}
      onMouseDown={stop}
      onClick={(e) => {
        stop(e)
        toggleFavorite(hotelId)
        pushToast(active ? 'Удалено из избранного' : 'Добавлено в избранное')
      }}
      whileTap={profile.reduce ? undefined : { scale: 0.9 }}
      whileHover={profile.reduce || profile.coarse ? undefined : { scale: 1.05 }}
      transition={springs.tap}
      className={`inline-flex h-11 w-11 items-center justify-center rounded-full border border-border bg-white text-brand-blue-900 transition-colors duration-150 hover:border-brand-green-400 hover:bg-brand-green-100 ${className}`}
    >
      <motion.span
        key={active ? 'on' : 'off'}
        initial={profile.reduce ? false : { scale: 0.7 }}
        animate={{ scale: 1 }}
        transition={springs.snappy}
        className="inline-flex"
      >
        <Heart
          size={18}
          className={active ? 'fill-error text-error' : 'text-brand-blue-900'}
          aria-hidden
        />
      </motion.span>
    </motion.button>
  )
}
