import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { HotelGallery } from '../components/HotelGallery'
import { BookingSidebar } from '../components/BookingSidebar'
import { RoomCard } from '../components/RoomCard'
import { RatingBadge } from '../components/RatingBadge'
import { FeatureChip } from '../components/FeatureChip'
import { FavoriteButton } from '../components/FavoriteButton'
import { EmptyState } from '../components/EmptyState'
import { SafeImage } from '../components/SafeImage'
import { useFlow } from '../context/FlowContext'
import { formatDateRu, getHotelById, nightsBetween } from '../data/hotels'
import { catalogToHotel, ensureCatalogReady, getCatalogHotelById } from '../data/catalogHotels'
import { Button } from '../components/Button'
import { resolveHotelCoords } from '../lib/hotelCoords'

function planTripPath(opts: {
  hotelId: string
  name: string
  city: string
  country: string
  lat?: number | null
  lon?: number | null
}) {
  const coords = resolveHotelCoords(opts.hotelId, opts.lat, opts.lon)
  const q = new URLSearchParams({
    hotelId: opts.hotelId,
    hotelName: opts.name,
    city: opts.city,
    country: opts.country,
  })
  if (coords) {
    q.set('lat', String(coords.lat))
    q.set('lon', String(coords.lon))
  }
  return `/oh-route?${q.toString()}`
}

export function HotelDetailScreen() {
  const { hotelId = '', id = '' } = useParams()
  const resolvedId = hotelId || id
  const navigate = useNavigate()
  const roomsRef = useRef<HTMLDivElement>(null)
  const [catalogReady, setCatalogReady] = useState(false)
  const {
    setSelectedHotel,
    setSelectedRoom,
    guests,
    setGuests,
    checkIn,
    checkOut,
    setCheckIn,
    setCheckOut,
    uploaded,
  } = useFlow()

  useEffect(() => {
    let cancelled = false
    void ensureCatalogReady().then(() => {
      if (!cancelled) setCatalogReady(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const catalogEntry = useMemo(
    () => (catalogReady ? getCatalogHotelById(resolvedId) : undefined),
    [catalogReady, resolvedId],
  )
  const hotel = useMemo(
    () => getHotelById(resolvedId) ?? (catalogEntry ? catalogToHotel(catalogEntry) : undefined),
    [resolvedId, catalogEntry],
  )
  const isCloudOnly = Boolean(catalogEntry && catalogEntry.source === 'hotels50k' && !getHotelById(resolvedId))
  const nights = nightsBetween(checkIn, checkOut)

  useEffect(() => {
    if (hotel) setSelectedHotel(hotel)
  }, [hotel, setSelectedHotel])

  useEffect(() => {
    if (!checkIn || checkOut > checkIn) return
    const [y, m, d] = checkIn.split('-').map(Number)
    if (!y || !m || !d) return
    const next = new Date(y, m - 1, d + 1)
    const iso = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`
    setCheckOut(iso)
  }, [checkIn, checkOut, setCheckOut])

  if (!hotel && !catalogReady) {
    return (
      <main className="page-container flex min-h-[40vh] items-center justify-center py-10 text-sm text-text-muted">
        Загрузка отеля…
      </main>
    )
  }

  if (!hotel) {
    return (
      <main className="page-container py-10">
        <EmptyState
          title="Отель не найден"
          description="Возможно, ссылка устарела. Вернитесь в каталог."
          actionLabel="В каталог"
          onAction={() => navigate('/catalog')}
        />
      </main>
    )
  }

  if (isCloudOnly) {
    return (
      <main className="page-container space-y-8 py-8 sm:py-10">
        <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
          <div className="space-y-6 lg:col-span-8">
            <HotelGallery images={hotel.images} name={hotel.name} hotelId={hotel.id} />
            <div>
              <p className="text-sm font-semibold text-brand-blue-800">
                {catalogEntry?.country
                  ? `${catalogEntry.country}${catalogEntry.city ? ` · ${catalogEntry.city}` : ''}`
                  : 'Hotels-50K · визуальный индекс'}
              </p>
              <h1 className="mt-2 text-3xl font-bold text-brand-blue-950 sm:text-4xl">{hotel.name}</h1>
              <p className="mt-2 text-[15px] text-text-secondary">
                {catalogEntry?.city && catalogEntry?.country
                  ? `${catalogEntry.city}, ${catalogEntry.country}`
                  : hotel.city}
                {catalogEntry?.latitude != null && catalogEntry.longitude != null
                  ? ` · ${catalogEntry.latitude.toFixed(3)}, ${catalogEntry.longitude.toFixed(3)}`
                  : ''}
              </p>
              <p className="mt-3 max-w-3xl text-[15px] leading-6 text-text-secondary">{hotel.description}</p>
              {hotel.amenities.length ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {hotel.amenities.map((item) => (
                    <FeatureChip key={item}>{item}</FeatureChip>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
          <div className="space-y-4 rounded-[24px] border border-border bg-white p-5 lg:col-span-4">
            <h2 className="text-lg font-bold text-brand-blue-950">Этот отель из облачной базы</h2>
            <p className="text-sm leading-5 text-text-secondary">
              Бронирование демо-номеров доступно для отелей локального каталога. Здесь можно
              посмотреть фото из индекса и найти похожий объект по своему снимку.
            </p>
            <Button
              fullWidth
              onClick={() =>
                navigate(
                  planTripPath({
                    hotelId: hotel.id,
                    name: hotel.name,
                    city: catalogEntry?.city || hotel.city,
                    country: catalogEntry?.country || hotel.country,
                    lat: catalogEntry?.latitude,
                    lon: catalogEntry?.longitude,
                  }),
                )
              }
            >
              Спланировать поездку
            </Button>

            <Button
              fullWidth
              variant="secondary"
              onClick={() => navigate(`/hotel-intelligence?hotelId=${encodeURIComponent(hotel.id)}`)}
            >
              О!Подбор: особенности отеля
            </Button>
            <Button fullWidth variant="secondary" onClick={() => navigate('/')}>
              Найти по фото
            </Button>
            <Button fullWidth variant="ghost" onClick={() => navigate('/catalog')}>
              Назад в каталог
            </Button>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="page-container space-y-8 py-8 sm:py-10">
      <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
        <div className="space-y-6 lg:col-span-8">
          <HotelGallery images={hotel.images} name={hotel.name} hotelId={hotel.id} />
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-brand-blue-950 sm:text-4xl">{hotel.name}</h1>
              <p className="mt-2 text-[15px] text-text-secondary">
                {hotel.city}, {hotel.country}
              </p>
              <p className="mt-1 text-sm text-text-muted">{hotel.address}</p>
              <div className="mt-3">
                <RatingBadge rating={hotel.rating} reviewCount={hotel.reviewCount} />
              </div>
            </div>
            <FavoriteButton hotelId={hotel.id} />
          </div>
          <p className="max-w-3xl text-[15px] leading-6 text-text-secondary">{hotel.description}</p>

          <div className="rounded-[20px] border border-border bg-surface-soft p-4 sm:p-5">
            <h2 className="text-lg font-bold text-brand-blue-950">Почему это похоже на ваше фото</h2>
            <p className="mt-2 text-[15px] text-text-secondary">
              Совпали {hotel.matchedFeatures.slice(0, 3).join(', ').toLowerCase()}.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              {uploaded ? (
                <SafeImage
                  src={uploaded.previewUrl}
                  alt="Ваше фото"
                  className="h-14 w-14 rounded-xl border border-border"
                />
              ) : null}
              <div className="flex flex-wrap gap-2">
                {hotel.matchedFeatures.map((item) => (
                  <FeatureChip key={item}>{item}</FeatureChip>
                ))}
              </div>
            </div>
          </div>

          <div>
            <h2 className="mb-3 text-xl font-bold text-brand-blue-950">Удобства</h2>
            <div className="flex flex-wrap gap-2">
              {hotel.amenities.slice(0, 7).map((item) => (
                <FeatureChip key={item}>{item}</FeatureChip>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-3 lg:col-span-4">
          <BookingSidebar
            pricePerNight={hotel.pricePerNight}
            priceStatus={catalogEntry?.price_status}
            nights={nights}
            guests={guests}
            checkIn={checkIn}
            checkOut={checkOut}
            onCheckInChange={setCheckIn}
            onCheckOutChange={(value) => {
              if (value > checkIn) setCheckOut(value)
            }}
            onGuestsChange={setGuests}
            onSelectRoom={() => roomsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
          />
          <Button
            fullWidth
            variant="soft"
            onClick={() =>
              navigate(
                planTripPath({
                  hotelId: hotel.id,
                  name: hotel.name,
                  city: hotel.city,
                  country: hotel.country,
                  lat: catalogEntry?.latitude,
                  lon: catalogEntry?.longitude,
                }),
              )
            }
          >
            Спланировать поездку
          </Button>
          <Button
            fullWidth
            variant="secondary"
            onClick={() => navigate(`/hotel-intelligence?hotelId=${encodeURIComponent(hotel.id)}`)}
          >
            О!Подбор: особенности отеля
          </Button>
        </div>
      </div>

      <section ref={roomsRef} className="space-y-4">
        <div>
          <h2 className="text-2xl font-bold text-brand-blue-950">Выберите номер</h2>
          <p className="mt-1 text-sm text-text-secondary">
            {formatDateRu(checkIn)} — {formatDateRu(checkOut)} · {nights} ноч.
          </p>
        </div>
        {hotel.rooms.map((room, index) => (
          <RoomCard
            key={room.id}
            room={room}
            nights={nights}
            index={index}
            onSelect={() => {
              setSelectedRoom({ ...room, nights, totalPrice: room.pricePerNight * nights })
              setSelectedHotel(hotel)
              navigate(`/checkout/${hotel.id}/${room.id}`)
            }}
          />
        ))}
      </section>
    </main>
  )
}
