import { useNavigate } from 'react-router-dom'
import { MapPin } from 'lucide-react'
import { motion } from 'framer-motion'
import type { CatalogHotel } from '../types/catalog'
import { RatingBadge } from './RatingBadge'
import { FeatureChip } from './FeatureChip'
import { FavoriteButton } from './FavoriteButton'
import { ImageCarousel } from './ImageCarousel'
import { SafeImage } from './SafeImage'
import { formatPrice } from '../lib/format'
import { MotionCard } from '../motion/MotionCard'

export function CatalogHotelCard({ hotel, index = 0 }: { hotel: CatalogHotel; index?: number }) {
  const navigate = useNavigate()
  const openHotel = () => navigate(`/hotel/${hotel.id}`)
  const place =
    hotel.city && hotel.country
      ? `${hotel.city}, ${hotel.country}`
      : hotel.chain && hotel.chain.toLowerCase() !== 'unknown'
        ? hotel.chain
        : hotel.country || 'Каталог'
  const chainLabel =
    hotel.chain && hotel.chain.toLowerCase() !== 'unknown' ? hotel.chain : null
  const showChainChip =
    Boolean(chainLabel) &&
    place !== chainLabel &&
    !hotel.name.toLowerCase().includes(chainLabel!.toLowerCase())
  const images = hotel.images.length ? hotel.images : []

  return (
    <MotionCard
      index={index}
      className="group relative flex h-full cursor-pointer flex-col overflow-hidden rounded-[24px] border border-border bg-white transition-[border-color,box-shadow] duration-200 ease-out hover:border-brand-green-400 hover:shadow-[0_8px_24px_rgba(14,23,77,0.06)]"
      onClick={openHotel}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          openHotel()
        }
      }}
      role="link"
      tabIndex={0}
      aria-label={`${hotel.name}, ${place}`}
    >
      {hotel.source === 'demo' ? (
        <div
          className="absolute right-3 top-3 z-20"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <FavoriteButton hotelId={hotel.id} />
        </div>
      ) : (
        <span className="absolute left-3 top-3 z-20 rounded-full bg-white/95 px-2.5 py-1 text-[11px] font-semibold text-brand-blue-950 shadow-sm">
          {hotel.image_count} фото
        </span>
      )}

      <motion.div layoutId={`hotel-cover-${hotel.id}`} className="overflow-hidden">
        {images.length > 1 ? (
          <ImageCarousel images={images} alt={hotel.name} className="aspect-[5/4]" eager={index < 3} />
        ) : images.length === 1 ? (
          <SafeImage src={images[0]} alt={hotel.name} className="aspect-[5/4]" eager={index < 3} />
        ) : (
          <div className="flex aspect-[5/4] items-center justify-center bg-surface-muted text-sm text-text-muted">
            Нет фото
          </div>
        )}
      </motion.div>

      <div className="flex flex-1 flex-col gap-3 p-4 sm:p-5">
        <div>
          <h3 className="text-lg font-bold leading-snug text-brand-blue-950 sm:text-xl">{hotel.name}</h3>
          <p className="mt-1.5 flex items-center gap-1.5 text-sm text-text-secondary">
            <MapPin size={14} className="shrink-0 text-brand-blue-800" aria-hidden />
            <span>{place}</span>
          </p>
        </div>

        {hotel.rating != null && hotel.rating > 0 ? (
          <RatingBadge rating={hotel.rating} reviewCount={hotel.reviewCount ?? 0} />
        ) : showChainChip && chainLabel ? (
          <FeatureChip>{chainLabel}</FeatureChip>
        ) : null}

        {hotel.description ? (
          <p className="line-clamp-2 text-sm leading-5 text-text-secondary">{hotel.description}</p>
        ) : null}

        {hotel.amenities?.length ? (
          <div className="flex flex-wrap gap-2">
            {hotel.amenities.slice(0, 3).map((amenity) => (
              <FeatureChip key={amenity}>{amenity}</FeatureChip>
            ))}
          </div>
        ) : null}

        <div className="mt-auto flex items-end justify-between gap-3 border-t border-border pt-3">
          <div>
            {hotel.pricePerNight != null && hotel.pricePerNight > 0 ? (
              <>
                <p className="text-xs font-medium text-text-muted">
                  {hotel.price_status === 'ui_estimate' ? 'ориентир' : 'от'}
                </p>
                <p className="text-lg font-bold text-brand-blue-950">
                  {formatPrice(hotel.pricePerNight)} ₽
                  <span className="text-sm font-medium text-text-secondary"> / ночь</span>
                </p>
                {hotel.price_status === 'ui_estimate' ? (
                  <p className="mt-0.5 text-[11px] text-text-muted">оценка, не оффер</p>
                ) : null}
              </>
            ) : (
              <p className="text-sm font-semibold text-text-secondary">Цена по запросу</p>
            )}
          </div>
          <span className="rounded-full bg-brand-green-100 px-3 py-1.5 text-xs font-semibold text-brand-blue-950 transition-colors group-hover:bg-brand-green-200">
            Смотреть
          </span>
        </div>
      </div>
    </MotionCard>
  )
}
