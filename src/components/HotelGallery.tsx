import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { SafeImage } from './SafeImage'
import { Button } from './Button'
import { Modal } from './Modal'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

export function HotelGallery({
  images,
  name,
  hotelId,
}: {
  images: string[]
  name: string
  hotelId?: string
}) {
  const list = images.length > 0 ? images : ['/fallback/hotel.jpg']
  const [active, setActive] = useState(0)
  const [openAll, setOpenAll] = useState(false)
  const index = ((active % list.length) + list.length) % list.length
  const profile = useMotionProfile()

  const go = (delta: number) => setActive((v) => v + delta)

  return (
    <div className="space-y-3">
      <motion.div
        layoutId={hotelId && !profile.reduce ? `hotel-cover-${hotelId}` : undefined}
        className="group relative overflow-hidden rounded-[24px] border border-border"
        transition={profile.reduce ? { duration: 0.12 } : springs.soft}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={list[index]}
            initial={profile.reduce ? false : { opacity: 0.72 }}
            animate={{ opacity: 1 }}
            exit={profile.reduce ? undefined : { opacity: 0.72 }}
            transition={{ duration: 0.2 }}
          >
            <SafeImage
              src={list[index]}
              alt={`${name} — фото ${index + 1}`}
              className="aspect-[16/10]"
              eager
            />
          </motion.div>
        </AnimatePresence>
        {list.length > 1 ? (
          <>
            <button
              type="button"
              aria-label="Предыдущее фото"
              className="absolute left-3 top-1/2 z-10 inline-flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-white/95 text-brand-blue-950 shadow-sm"
              onClick={() => go(-1)}
            >
              <ChevronLeft size={20} aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Следующее фото"
              className="absolute right-3 top-1/2 z-10 inline-flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-white/95 text-brand-blue-950 shadow-sm"
              onClick={() => go(1)}
            >
              <ChevronRight size={20} aria-hidden />
            </button>
            <div className="pointer-events-none absolute inset-x-0 bottom-3 z-10 flex justify-center gap-1.5">
              {list.map((_, i) => (
                <span
                  key={i}
                  className={`h-1.5 rounded-full ${i === index ? 'w-4 bg-white' : 'w-1.5 bg-white/55'}`}
                />
              ))}
            </div>
          </>
        ) : null}
        <div className="absolute bottom-3 right-3 z-10">
          <Button size="sm" variant="secondary" onClick={() => setOpenAll(true)}>
            Все фото
          </Button>
        </div>
      </motion.div>
      <div className="grid grid-cols-4 gap-2 sm:gap-3">
        {list.slice(0, 4).map((image, i) => (
          <button
            key={`${image}-${i}`}
            type="button"
            onClick={() => setActive(i)}
            className={`overflow-hidden rounded-2xl border transition-colors ${
              index === i ? 'border-brand-blue-700' : 'border-border'
            }`}
            aria-label={`Показать фото ${i + 1}`}
          >
            <SafeImage src={image} alt="" className="aspect-[4/3]" eager />
          </button>
        ))}
      </div>

      <Modal open={openAll} title={`Фото — ${name}`} onClose={() => setOpenAll(false)}>
        <div className="grid max-h-[60vh] grid-cols-2 gap-3 overflow-auto">
          {list.map((image, i) => (
            <button
              key={`${image}-all-${i}`}
              type="button"
              onClick={() => {
                setActive(i)
                setOpenAll(false)
              }}
              className="overflow-hidden rounded-2xl border border-border"
            >
              <SafeImage src={image} alt={`${name} ${i + 1}`} className="aspect-[4/3]" />
            </button>
          ))}
        </div>
      </Modal>
    </div>
  )
}
