import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { SimilarHotel } from '../types/hotel'
import { RatingBadge } from './RatingBadge'
import { FeatureChip } from './FeatureChip'
import { Button } from './Button'
import { FavoriteButton } from './FavoriteButton'
import { ImageCarousel } from './ImageCarousel'
import { formatPrice } from '../lib/format'
import { getHotelById } from '../data/hotels'
import { MotionCard } from '../motion/MotionCard'

export function SimilarHotelCard({ hotel, index = 0 }: { hotel: SimilarHotel; index?: number }) {
  const navigate = useNavigate()
  const openHotel = () => navigate(`/hotel/${hotel.hotelId}`)
  const full = getHotelById(hotel.hotelId)
  const images = full?.images?.length ? full.images : [hotel.image]

  return (
    <MotionCard
      index={index}
      className="group relative flex h-full flex-col overflow-hidden rounded-[20px] border border-border bg-white transition-[border-color,box-shadow] duration-200 ease-out hover:border-brand-green-400 hover:shadow-sm"
    >
      <div
        className="absolute right-3 top-3 z-20"
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
        }}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <FavoriteButton hotelId={hotel.hotelId} />
      </div>
      <motion.div layoutId={`hotel-cover-${hotel.hotelId}`} className="overflow-hidden">
        <ImageCarousel images={images} alt={hotel.name} className="aspect-[4/3]" eager />
      </motion.div>
      <div className="flex flex-1 flex-col gap-3 p-4 sm:p-5">
        <button type="button" className="text-left" onClick={openHotel}>
          <h3 className="text-lg font-bold text-brand-blue-950">{hotel.name}</h3>
          <p className="text-sm text-text-secondary">
            {hotel.city}, {hotel.country}
          </p>
        </button>
        <RatingBadge rating={hotel.rating} reviewCount={hotel.reviewCount} />
        <div>
          {hotel.pricePerNight > 0 ? (
            <>
              <p className="text-lg font-bold text-text-primary">
                <span className="mr-1 text-sm font-medium text-text-secondary">Ориентир</span>
                {formatPrice(hotel.pricePerNight)} ₽ / ночь
              </p>
              {hotel.savings > 0 ? (
                <p className="text-sm font-semibold text-success">На {formatPrice(hotel.savings)} ₽ дешевле</p>
              ) : null}
            </>
          ) : (
            <p className="text-sm font-semibold text-text-secondary">Цена по запросу</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {hotel.features.slice(0, 2).map((feature) => (
            <FeatureChip key={feature}>{feature}</FeatureChip>
          ))}
        </div>
        <div className="mt-auto pt-2">
          <Button variant="secondary" fullWidth onClick={openHotel}>
            Посмотреть
          </Button>
        </div>
      </div>
    </MotionCard>
  )
}
