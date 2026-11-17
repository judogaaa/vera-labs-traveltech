import { motion } from 'framer-motion'
import { ImageCarousel } from './ImageCarousel'
import { MatchBadge } from './MatchBadge'
import { RatingBadge } from './RatingBadge'
import { PriceBlock } from './PriceBlock'
import { FeatureChip } from './FeatureChip'
import { Button } from './Button'
import { FavoriteButton } from './FavoriteButton'
import type { Hotel } from '../types/hotel'
import type { HotelMatchLevel } from '../types/vision'
import { MotionCard } from '../motion/MotionCard'

export function HotelMatchCard({
  hotel,
  matchLevel,
  matchedFeatures,
  imageUrl,
  onConfirm,
  onReject,
}: {
  hotel: Hotel
  matchLevel: HotelMatchLevel
  matchedFeatures: string[]
  imageUrl?: string
  onConfirm: () => void
  onReject: () => void
}) {
  const safeMatched =
    imageUrl && !/image-submissions\.s3|traffickcam/i.test(imageUrl) ? imageUrl : undefined
  const gallery = safeMatched
    ? [safeMatched, ...hotel.images.filter((src) => src !== safeMatched)]
    : hotel.images

  return (
    <MotionCard className="overflow-hidden rounded-[24px] border border-border bg-white shadow-[0_1px_2px_rgba(21,23,28,0.04)]">
      <div className="grid min-h-[420px] gap-0 lg:grid-cols-[1.55fr_1fr]">
        <motion.div layoutId={`hotel-cover-${hotel.id}`} className="min-h-0 overflow-hidden">
          <ImageCarousel
            images={gallery}
            alt={hotel.name}
            className="aspect-[16/10] min-h-[240px] lg:aspect-auto lg:h-full lg:min-h-full"
            eager
          />
        </motion.div>
        <div className="relative flex flex-col gap-4 p-5 sm:p-7">
          <div className="absolute right-4 top-4 z-20">
            <FavoriteButton hotelId={hotel.id} />
          </div>
          <MatchBadge level={matchLevel} />
          <div className="pr-12">
            <h2 className="text-[28px] font-bold leading-tight text-brand-blue-950 sm:text-[32px]">
              {hotel.name}
            </h2>
            <p className="mt-1 text-[15px] text-text-secondary">
              {hotel.city}, {hotel.country}
            </p>
          </div>
          <RatingBadge rating={hotel.rating} reviewCount={hotel.reviewCount} />
          <PriceBlock pricePerNight={hotel.pricePerNight} large />
          <div>
            <p className="mb-2 text-sm font-semibold text-text-primary">Что совпало</p>
            <div className="flex flex-wrap gap-2">
              {matchedFeatures.map((feature) => (
                <FeatureChip key={feature}>{feature}</FeatureChip>
              ))}
            </div>
          </div>
          <div className="mt-auto flex flex-col gap-3 pt-2 sm:flex-row">
            <Button onClick={onConfirm} fullWidth>
              Посмотреть номера
            </Button>
            <Button variant="secondary" onClick={onReject} fullWidth>
              Это не тот отель
            </Button>
          </div>
        </div>
      </div>
    </MotionCard>
  )
}
