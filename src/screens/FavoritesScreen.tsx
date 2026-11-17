import { useNavigate } from 'react-router-dom'
import { EmptyState } from '../components/EmptyState'
import { SimilarHotelCard } from '../components/SimilarHotelCard'
import { useFlow } from '../context/FlowContext'
import { getHotelById, similarCheaper } from '../data/hotels'

export function FavoritesScreen() {
  const navigate = useNavigate()
  const { favorites } = useFlow()

  const items = favorites
    .map((id) => {
      const hotel = getHotelById(id)
      if (!hotel) return null
      return {
        hotelId: hotel.id,
        name: hotel.name,
        city: hotel.city,
        country: hotel.country,
        rating: hotel.rating,
        reviewCount: hotel.reviewCount,
        pricePerNight: hotel.pricePerNight,
        savings: 0,
        image: hotel.images[0],
        features: hotel.matchedFeatures.slice(0, 2),
      }
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))

  return (
    <main className="page-container space-y-8 py-8 sm:py-10">
      <div>
        <h1 className="text-3xl font-bold text-brand-blue-950 sm:text-4xl">Избранное</h1>
        <p className="mt-2 text-text-secondary">
          {items.length > 0 ? `${items.length} сохранённых отелей` : 'Сохранённые отели появятся здесь.'}
        </p>
      </div>

      {items.length === 0 ? (
        <>
          <EmptyState
            title="Пока пусто"
            description="Добавляйте отели сердечком — они сохранятся на этом устройстве."
            actionLabel="Найти отель"
            onAction={() => navigate('/')}
          />
          <section>
            <h2 className="mb-4 text-xl font-bold text-brand-blue-950">Возможно, вам понравится</h2>
            <div className="grid gap-4 md:grid-cols-3">
              {similarCheaper.slice(0, 3).map((hotel) => (
                <SimilarHotelCard key={hotel.hotelId} hotel={hotel} />
              ))}
            </div>
          </section>
        </>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((hotel) => (
            <SimilarHotelCard key={hotel.hotelId} hotel={hotel} />
          ))}
        </div>
      )}
    </main>
  )
}
