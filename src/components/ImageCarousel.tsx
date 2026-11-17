import { useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { SafeImage } from './SafeImage'

type ImageCarouselProps = {
  images: string[]
  alt: string
  className?: string
  eager?: boolean
}

export function ImageCarousel({
  images,
  alt,
  className = 'aspect-[4/3]',
  eager = true,
}: ImageCarouselProps) {
  const list = images.filter(Boolean).length > 0 ? images.filter(Boolean) : ['/fallback/hotel.jpg']
  const [index, setIndex] = useState(0)
  const startX = useRef<number | null>(null)
  const active = ((index % list.length) + list.length) % list.length

  const go = (delta: number, e?: React.SyntheticEvent) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    setIndex((v) => v + delta)
  }

  return (
    <div
      className={`group/carousel relative overflow-hidden bg-surface-muted ${className}`}
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => {
        startX.current = e.clientX
      }}
      onPointerUp={(e) => {
        if (startX.current == null || list.length < 2) return
        const dx = e.clientX - startX.current
        startX.current = null
        if (Math.abs(dx) < 40) return
        e.preventDefault()
        e.stopPropagation()
        go(dx < 0 ? 1 : -1)
      }}
      onPointerCancel={() => {
        startX.current = null
      }}
      role="group"
      aria-roledescription="carousel"
      aria-label={`Фото: ${alt}`}
    >
      <SafeImage
        src={list[active]}
        alt={`${alt} — фото ${active + 1}`}
        className="absolute inset-0 h-full w-full"
        eager={eager}
      />

      {list.length > 1 ? (
        <>
          <button
            type="button"
            aria-label="Предыдущее фото"
            className="absolute left-2 top-1/2 z-10 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-white/95 text-brand-blue-950 shadow-sm sm:opacity-0 sm:group-hover/carousel:opacity-100"
            onClick={(e) => go(-1, e)}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <ChevronLeft size={18} aria-hidden />
          </button>
          <button
            type="button"
            aria-label="Следующее фото"
            className="absolute right-2 top-1/2 z-10 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-white/95 text-brand-blue-950 shadow-sm sm:opacity-0 sm:group-hover/carousel:opacity-100"
            onClick={(e) => go(1, e)}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <ChevronRight size={18} aria-hidden />
          </button>
          <div className="pointer-events-none absolute inset-x-0 bottom-2 z-10 flex justify-center gap-1.5">
            {list.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 rounded-full transition-all ${
                  i === active ? 'w-4 bg-white' : 'w-1.5 bg-white/55'
                }`}
              />
            ))}
          </div>
        </>
      ) : null}
    </div>
  )
}
