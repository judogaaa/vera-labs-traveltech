import { useNavigate } from 'react-router-dom'
import { SimilarHotelCard } from '../components/SimilarHotelCard'
import { Button } from '../components/Button'
import { similarCheaper } from '../data/hotels'

export function NoExactMatchScreen() {
  const navigate = useNavigate()

  return (
    <main className="page-container space-y-8 py-8 sm:py-10">
      <div>
        <h1 className="text-3xl font-bold text-brand-blue-950 sm:text-4xl">Точного совпадения не нашли</h1>
        <p className="mt-2 max-w-2xl text-text-secondary">
          Покажем варианты с похожей атмосферой и характеристиками.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {similarCheaper.map((hotel) => (
          <SimilarHotelCard key={hotel.hotelId} hotel={hotel} />
        ))}
      </div>

      <div className="rounded-[20px] bg-surface-soft p-5">
        <p className="text-[15px] text-text-secondary">
          Похожи бассейн, открытая территория и общий курортный характер фотографии.
        </p>
        <div className="mt-4">
          <Button variant="secondary" onClick={() => navigate('/')}>
            Загрузить другое фото
          </Button>
        </div>
      </div>
    </main>
  )
}
