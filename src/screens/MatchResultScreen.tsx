import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { HotelMatchCard } from '../components/HotelMatchCard'
import { SimilarHotelCard } from '../components/SimilarHotelCard'
import { EmptyState } from '../components/EmptyState'
import { SafeImage } from '../components/SafeImage'
import { RatingBadge } from '../components/RatingBadge'
import { FeatureChip } from '../components/FeatureChip'
import { Button } from '../components/Button'
import { FavoriteButton } from '../components/FavoriteButton'
import { PageEnter } from '../components/PageEnter'
import { ImageCarousel } from '../components/ImageCarousel'
import { useFlow } from '../context/FlowContext'
import { isRegionSearchMode } from '../types/visualSearch'
import { getHotelById, similarCheaper } from '../data/hotels'
import { formatPrice } from '../lib/format'
import type { Hotel } from '../types/hotel'
import type { HotelMatch } from '../types/vision'

const TRAFFICKCAM_IMAGE_RE = /image-submissions\.s3|traffickcam/i

function hotelFromCloudMatch(match: HotelMatch): Hotel | null {
  const cover = match.matchedImageUrl
  // Never surface crowd-sourced dump frames as product cards.
  if (cover && TRAFFICKCAM_IMAGE_RE.test(cover)) return null
  if (!match.hotelName?.trim()) return null
  return {
    id: match.hotelId,
    name: match.hotelName,
    city: match.chain?.trim() || 'Курорт',
    country: '',
    address: '',
    rating: 0,
    reviewCount: 0,
    pricePerNight: 0,
    images: cover ? [cover] : [],
    amenities: [],
    description: 'Вариант из визуального поиска.',
    matchedFeatures: match.matchedFeatures,
    visualTags: match.matchedFeatures,
    rooms: [],
  }
}

function galleryForMatch(hotel: Hotel, matchedImageUrl?: string): string[] {
  if (matchedImageUrl && !TRAFFICKCAM_IMAGE_RE.test(matchedImageUrl)) {
    return [matchedImageUrl, ...hotel.images.filter((src) => src !== matchedImageUrl)]
  }
  return hotel.images
}

export function MatchResultScreen() {
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const { matches, uploaded, visualSearch, setSelectedHotel, analysis } = useFlow()
  const isRegion = isRegionSearchMode(visualSearch?.mode)

  const ranked = useMemo(() => {
    return matches
      .map((match) => {
        const hotel =
          getHotelById(match.hotelId) ?? (match.source === 'cloud' ? hotelFromCloudMatch(match) : null)
        if (!hotel || hotel.images.length === 0) return null
        return { hotel, match }
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
  }, [matches])

  const primary = ranked[0] ?? null
  const hasExact = Boolean(primary?.match.isExactCandidate || primary?.match.matchLevel === 'very-high')
  const hasStrong = ranked.some((r) => r.match.matchLevel === 'very-high' || r.match.matchLevel === 'high')

  if (!uploaded || !visualSearch) {
    return (
      <main className="page-container py-10">
        <EmptyState
          title="Начните новый поиск"
          description="Сессия поиска не найдена. Загрузите фото ещё раз."
          actionLabel="На главную"
          onAction={() => navigate('/')}
        />
      </main>
    )
  }

  if (!primary) {
    return (
      <main className="page-container py-10">
        <EmptyState
          title="Точного совпадения не нашли"
          description="Вот варианты с похожей атмосферой из демо-каталога."
          actionLabel="К похожим"
          onAction={() => navigate('/search/no-match')}
        />
      </main>
    )
  }

  if (isRegion) {
    const reason =
      analysis?.detectedFeatures?.slice(0, 2).join(' и ') ||
      primary.match.matchedFeatures.slice(0, 2).join(' и ')
    const poolLike = analysis?.detectedFeatures.some((t) => /басс|вод/i.test(t))

    return (
      <main className="page-container space-y-10 py-8 sm:py-10">
        <PageEnter>
          <p className="text-sm font-semibold text-brand-blue-800">Искали по выделенной детали</p>
          <h1 className="mt-2 text-3xl font-bold text-brand-blue-950 sm:text-4xl">
            {poolLike ? 'Нашли похожие бассейны' : 'Нашли варианты с похожей деталью'}
          </h1>
          <p className="mt-2 text-text-secondary">
            Сравнили выделенную область с фотографиями объектов демо-каталога.
          </p>
          {visualSearch.cropPreviewUrl ? (
            <div className="mt-4 flex items-center gap-3">
              <SafeImage
                src={visualSearch.cropPreviewUrl}
                alt="Выделенная деталь"
                className="h-16 w-16 rounded-xl border border-border"
              />
              <p className="text-sm text-text-secondary">Вы искали по этой области · похожие {reason.toLowerCase()}</p>
            </div>
          ) : null}
        </PageEnter>

        <section className="space-y-4">
          <h2 className="text-xl font-bold text-brand-blue-950">Больше всего похоже</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {ranked.map(({ hotel, match }, index) => (
              <motion.article
                key={hotel.id}
                className="relative overflow-hidden rounded-[20px] border border-border bg-white transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-brand-green-400 hover:shadow-sm"
                initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
                animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
                transition={{ duration: 0.24, delay: reduce ? 0 : index * 0.05 }}
              >
                <div
                  className="absolute right-3 top-3 z-20"
                  onClick={(e) => e.stopPropagation()}
                  onPointerDown={(e) => e.stopPropagation()}
                >
                  <FavoriteButton hotelId={hotel.id} />
                </div>
                {index === 0 ? (
                  <span className="absolute left-3 top-3 z-10 rounded-full bg-brand-green-100 px-3 py-1 text-xs font-semibold text-brand-blue-950">
                    Больше всего похоже
                  </span>
                ) : null}
                <ImageCarousel
                  images={galleryForMatch(hotel, match.matchedImageUrl)}
                  alt={hotel.name}
                  className="aspect-[4/3]"
                  eager={index === 0}
                />
                <div className="space-y-3 p-4">
                  <div>
                    <h3 className="text-lg font-bold text-brand-blue-950">{hotel.name}</h3>
                    <p className="text-sm text-text-secondary">
                      {[hotel.city, hotel.country].filter(Boolean).join(', ')}
                    </p>
                  </div>
                  {hotel.rating > 0 ? (
                    <RatingBadge rating={hotel.rating} reviewCount={hotel.reviewCount} />
                  ) : null}
                  {hotel.pricePerNight > 0 ? (
                    <p className="text-lg font-bold">
                      <span className="mr-1 text-sm font-medium text-text-secondary">Ориентир</span>
                      {formatPrice(hotel.pricePerNight)} ₽ / ночь
                    </p>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    {match.matchedFeatures
                      .filter((f) => !/unknown|hotels-?50k/i.test(f))
                      .slice(0, 3)
                      .map((f) => (
                        <FeatureChip key={f}>{f}</FeatureChip>
                      ))}
                  </div>
                  <Button
                    fullWidth
                    variant={index === 0 ? 'primary' : 'secondary'}
                    onClick={() => {
                      setSelectedHotel(hotel)
                      navigate(`/hotel/${hotel.id}`)
                    }}
                  >
                    Посмотреть
                  </Button>
                </div>
              </motion.article>
            ))}
          </div>
        </section>

        <CheaperSection />
      </main>
    )
  }

  return (
    <main className="page-container space-y-10 py-8 sm:py-10">
      <PageEnter>
        <p className="text-sm font-semibold text-brand-blue-800">
          {hasExact
            ? 'Очень высокое совпадение'
            : hasStrong
              ? 'Высокое совпадение'
              : 'Возможное совпадение'}
        </p>
        <h1 className="mt-2 text-3xl font-bold text-brand-blue-950 sm:text-4xl">
          {hasExact ? 'Похоже, это он' : hasStrong ? 'Нашли несколько возможных вариантов' : 'Точного совпадения не нашли'}
        </h1>
        <p className="mt-2 text-text-secondary">
          {primary.match.source === 'cloud'
            ? 'Сравнение по embedding в облачной базе Hotels-50K / Qdrant. matchedImage — ближайший найденный кадр.'
            : hasExact
              ? 'Нашли объект с совпадающими фотографиями в демо-каталоге.'
              : 'Показали ближайшие варианты из локального каталога — без ложной точности.'}
        </p>
      </PageEnter>

      <PageEnter delay={0.05}>
        <HotelMatchCard
          hotel={primary.hotel}
          matchLevel={primary.match.matchLevel}
          matchedFeatures={primary.match.matchedFeatures}
          imageUrl={primary.match.matchedImageUrl}
          onConfirm={() => {
            setSelectedHotel(primary.hotel)
            navigate(`/hotel/${primary.hotel.id}`)
          }}
          onReject={() => navigate('/search/matches')}
        />
      </PageEnter>

      <CheaperSection />
    </main>
  )
}

function CheaperSection() {
  const reduce = useReducedMotion()
  return (
    <section>
      <div className="mb-5">
        <h2 className="text-2xl font-bold text-brand-blue-950 sm:text-[28px]">О! Похожее дешевле</h2>
        <p className="mt-2 text-text-secondary">Похожие детали и атмосфера — за меньшую цену.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {similarCheaper.map((hotel, index) => (
          <motion.div
            key={hotel.hotelId}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
            transition={{ duration: 0.22, delay: reduce ? 0 : 0.08 + index * 0.05 }}
          >
            <SimilarHotelCard hotel={hotel} />
          </motion.div>
        ))}
      </div>
    </section>
  )
}
