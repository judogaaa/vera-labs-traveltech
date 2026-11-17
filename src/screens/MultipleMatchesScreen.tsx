import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { MatchBadge } from '../components/MatchBadge'
import { RatingBadge } from '../components/RatingBadge'
import { EmptyState } from '../components/EmptyState'
import { FavoriteButton } from '../components/FavoriteButton'
import { ImageCarousel } from '../components/ImageCarousel'
import { useFlow } from '../context/FlowContext'
import { getHotelById, multipleMatchHotelIds } from '../data/hotels'
import type { HotelMatchLevel } from '../types/vision'

const levels: HotelMatchLevel[] = ['high', 'high', 'possible', 'possible']

export function MultipleMatchesScreen() {
  const navigate = useNavigate()
  const { setSelectedHotel, uploaded } = useFlow()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const cards = useMemo(
    () =>
      multipleMatchHotelIds
        .map((id, index) => {
          const hotel = getHotelById(id)
          if (!hotel) return null
          return { hotel, level: levels[index] }
        })
        .filter((item): item is { hotel: NonNullable<ReturnType<typeof getHotelById>>; level: HotelMatchLevel } =>
          Boolean(item),
        ),
    [],
  )

  if (!uploaded) {
    return (
      <main className="page-container py-10">
        <EmptyState
          title="Нет загруженного фото"
          description="Загрузите фото, чтобы увидеть возможные совпадения."
          actionLabel="На главную"
          onAction={() => navigate('/')}
        />
      </main>
    )
  }

  return (
    <main className="page-container space-y-8 py-8 sm:py-10">
      <div>
        <h1 className="text-3xl font-bold text-brand-blue-950 sm:text-4xl">
          Нашли несколько возможных совпадений
        </h1>
        <p className="mt-2 text-text-secondary">Какой вариант больше похож на тот, что вы искали?</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {cards.map(({ hotel, level }) => {
          const selected = selectedId === hotel.id
          return (
            <div
              key={hotel.id}
              className={`relative overflow-hidden rounded-[20px] border bg-white ${
                selected ? 'border-brand-blue-700' : 'border-border'
              }`}
            >
              <div className="absolute right-3 top-3 z-20">
                <FavoriteButton hotelId={hotel.id} />
              </div>
              <ImageCarousel images={hotel.images} alt={hotel.name} className="aspect-[16/10]" eager />
              <button type="button" className="w-full text-left" onClick={() => setSelectedId(hotel.id)}>
                <div className="space-y-3 p-4">
                  <MatchBadge level={level} />
                  <div>
                    <h2 className="text-lg font-bold text-brand-blue-950">{hotel.name}</h2>
                    <p className="text-sm text-text-secondary">
                      {hotel.city}, {hotel.country}
                    </p>
                  </div>
                  <RatingBadge rating={hotel.rating} reviewCount={hotel.reviewCount} />
                </div>
              </button>
            </div>
          )
        })}
      </div>

      <div className="sticky bottom-4 z-20 rounded-[20px] border border-border bg-white/95 p-4 shadow-sm backdrop-blur">
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button
            fullWidth
            disabled={!selectedId}
            onClick={() => {
              const hotel = cards.find((c) => c.hotel.id === selectedId)?.hotel
              if (!hotel) return
              setSelectedHotel(hotel)
              navigate(`/hotel/${hotel.id}`)
            }}
          >
            Да, похоже на него
          </Button>
          <Button variant="secondary" fullWidth onClick={() => navigate('/search/no-match')}>
            Ни один не подходит
          </Button>
        </div>
      </div>
    </main>
  )
}
