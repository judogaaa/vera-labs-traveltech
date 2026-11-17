import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { Button } from '../components/Button'
import { Modal } from '../components/Modal'
import { Input } from '../components/Input'
import { SafeImage } from '../components/SafeImage'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState } from '../components/EmptyState'
import { useFlow } from '../context/FlowContext'
import { formatDateRu, getHotelById } from '../data/hotels'
import { formatPrice } from '../lib/format'
import { readStorage, STORAGE_KEYS } from '../lib/storage'
import { updateGuest } from '../services/bookingService'
import type { PlannedTrip } from '../types/trip'

export function TripsScreen() {
  const navigate = useNavigate()
  const { bookings } = useFlow()
  const planned = useMemo(() => readStorage<PlannedTrip[]>(STORAGE_KEYS.plannedTrips, []), [])

  if (bookings.length === 0 && planned.length === 0) {
    return (
      <main className="page-container py-10">
        <h1 className="mb-6 text-3xl font-bold text-brand-blue-950">Мои поездки</h1>
        <EmptyState
          title="Пока нет активных поездок"
          description="Забронируйте отель или соберите маршрут в О!Маршрут."
          actionLabel="О!Маршрут"
          onAction={() => navigate('/oh-route')}
        />
      </main>
    )
  }

  return (
    <main className="page-container space-y-8 py-8 sm:py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold text-brand-blue-950">Мои поездки</h1>
          <p className="mt-2 text-text-secondary">
            {bookings.length} бронирований · {planned.length} маршрутов О!Маршрут
          </p>
        </div>
        <Button variant="soft" onClick={() => navigate('/oh-route')}>
          Новый маршрут
        </Button>
      </div>

      {planned.length > 0 ? (
        <section className="space-y-4">
          <h2 className="text-xl font-bold text-brand-blue-950">О!Маршрут</h2>
          <div className="grid gap-4">
            {planned.map((trip) => (
              <article key={trip.id} className="rounded-[20px] border border-border bg-white p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-bold text-brand-blue-950">{trip.destination.name}</h3>
                    <p className="mt-1 text-sm text-text-secondary">
                      {trip.days.length} дн. · {trip.days.reduce((n, d) => n + d.stops.length, 0)} мест
                      {trip.hotel?.name ? ` · база: ${trip.hotel.name}` : ''}
                    </p>
                    <p className="mt-2 text-sm text-text-muted">{trip.summary}</p>
                  </div>
                  <Link to={`/oh-route?trip=${trip.id}`} className="no-underline">
                    <Button>Открыть маршрут</Button>
                  </Link>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {bookings.length > 0 ? (
        <section className="space-y-4">
          <h2 className="text-xl font-bold text-brand-blue-950">Бронирования</h2>
          <div className="grid gap-4">
            {bookings.map((booking) => {
              const hotel = getHotelById(booking.hotelId)
              if (!hotel) return null
              const room = hotel.rooms.find((r) => r.id === booking.roomId)
              return (
                <article key={booking.id} className="overflow-hidden rounded-[20px] border border-border bg-white">
                  <div className="grid gap-0 md:grid-cols-[240px_1fr]">
                    <SafeImage src={hotel.images[0]} alt={hotel.name} className="min-h-[180px]" />
                    <div className="flex flex-col gap-3 p-5">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h2 className="text-xl font-bold text-brand-blue-950">{hotel.name}</h2>
                          <p className="text-sm text-text-secondary">
                            {hotel.city}, {hotel.country}
                          </p>
                        </div>
                        <StatusBadge>Оплачено</StatusBadge>
                      </div>
                      <p className="text-sm text-text-secondary">
                        {formatDateRu(booking.checkIn)} — {formatDateRu(booking.checkOut)} · {booking.guests} гостя ·{' '}
                        {room?.name}
                      </p>
                      <p className="text-sm text-text-muted">Бронь {booking.id}</p>
                      <div className="mt-auto flex flex-wrap gap-2 pt-2">
                        <Link to={`/trips/${booking.id}`} className="no-underline sm:max-w-[220px] sm:flex-1">
                          <Button fullWidth>Открыть поездку</Button>
                        </Link>
                        <Button
                          variant="soft"
                          onClick={() =>
                            navigate(
                              `/oh-route?hotelId=${hotel.id}&hotelName=${encodeURIComponent(hotel.name)}&city=${encodeURIComponent(hotel.city)}&country=${encodeURIComponent(hotel.country)}`,
                            )
                          }
                        >
                          Спланировать маршрут
                        </Button>
                      </div>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        </section>
      ) : null}
    </main>
  )
}

export function MyTripScreen() {
  const { bookingId = '' } = useParams()
  const navigate = useNavigate()
  const { bookings, updateBookingGuest, pushToast, contact, setContact } = useFlow()
  const booking = useMemo(
    () => bookings.find((b) => b.id === bookingId) ?? null,
    [bookings, bookingId],
  )
  const hotel = booking ? getHotelById(booking.hotelId) : null
  const room = hotel?.rooms.find((item) => item.id === booking?.roomId) ?? null
  const [modal, setModal] = useState<string | null>(null)
  const [guestForm, setGuestForm] = useState({ firstName: '', lastName: '' })
  const [message, setMessage] = useState('')

  if (!booking || !hotel || !room) {
    return (
      <main className="page-container py-10">
        <EmptyState
          title="Пока нет активных поездок"
          description="После бронирования здесь появится управление поездкой."
          actionLabel="Найти отель"
          onAction={() => navigate('/')}
        />
      </main>
    )
  }

  return (
    <main className="page-container space-y-6 py-8 sm:py-10">
      <div>
        <h1 className="text-3xl font-bold text-brand-blue-950 sm:text-4xl">Моя поездка</h1>
        <p className="mt-2 text-text-secondary">
          {hotel.name} · {formatDateRu(booking.checkIn)} — {formatDateRu(booking.checkOut)}
        </p>
      </div>

      <div className="overflow-hidden rounded-[22px] border border-border bg-white">
        <SafeImage src={hotel.images[0]} alt={hotel.name} className="aspect-[21/9]" />
        <div className="space-y-3 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-brand-blue-950">{hotel.name}</h2>
              <p className="text-sm text-text-secondary">
                {hotel.city}, {hotel.country}
              </p>
            </div>
            <StatusBadge>Оплачено</StatusBadge>
          </div>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-text-muted">Даты</dt>
              <dd className="font-medium">
                {formatDateRu(booking.checkIn)} — {formatDateRu(booking.checkOut)}
              </dd>
            </div>
            <div>
              <dt className="text-text-muted">Гости</dt>
              <dd className="font-medium">{booking.guests}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Номер</dt>
              <dd className="font-medium">{room.name}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Сумма</dt>
              <dd className="font-medium">{formatPrice(booking.totalPrice)} ₽</dd>
            </div>
            <div>
              <dt className="text-text-muted">Номер брони</dt>
              <dd className="font-medium">{booking.id}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Check-in</dt>
              <dd className="font-medium">с 14:00</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-text-muted">Адрес</dt>
              <dd className="font-medium">{hotel.address}</dd>
            </div>
          </dl>
        </div>
      </div>

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-[20px] border border-border bg-white p-5">
          <h2 className="text-lg font-bold text-brand-blue-950">До поездки</h2>
          <ul className="mt-3 space-y-2 text-sm text-text-secondary">
            <li>Бесплатная отмена до 12 июня</li>
            <li>Документы готовы</li>
            <li>{hotel.address}</li>
            <li>Check-in с 14:00</li>
          </ul>
        </div>
        <div className="rounded-[20px] border border-border bg-white p-5">
          <h2 className="text-lg font-bold text-brand-blue-950">Бронирование</h2>
          <ul className="mt-3 space-y-2 text-sm text-text-secondary">
            <li>Номер брони: {booking.id}</li>
            <li>Статус оплаты: Оплачено</li>
            <li>
              Гости: {booking.contact.firstName} {booking.contact.lastName}
            </li>
          </ul>
        </div>
        <div className="rounded-[20px] border border-border bg-white p-5">
          <h2 className="text-lg font-bold text-brand-blue-950">Что можно сделать</h2>
          <div className="mt-3 flex flex-col gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setGuestForm({
                  firstName: booking.contact.firstName,
                  lastName: booking.contact.lastName,
                })
                setModal('guests')
              }}
            >
              Изменить данные гостей
            </Button>
            <Button variant="secondary" onClick={() => setModal('contact')}>
              Связаться с объектом
            </Button>
            <Button variant="secondary" onClick={() => setModal('cancel')}>
              Условия отмены
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setModal('download')
                pushToast('Подтверждение подготовлено')
              }}
            >
              Скачать подтверждение
            </Button>
          </div>
        </div>
      </section>

      <Modal open={modal === 'guests'} title="Данные гостей" onClose={() => setModal(null)}>
        <div className="space-y-3">
          <Input
            label="Имя"
            value={guestForm.firstName}
            onChange={(e) => setGuestForm({ ...guestForm, firstName: e.target.value })}
          />
          <Input
            label="Фамилия"
            value={guestForm.lastName}
            onChange={(e) => setGuestForm({ ...guestForm, lastName: e.target.value })}
          />
          <Button
            fullWidth
            onClick={() => {
              void updateGuest(booking.id, {
                ...booking.contact,
                firstName: guestForm.firstName,
                lastName: guestForm.lastName,
              }).then(() => {
                updateBookingGuest(booking.id, {
                  ...booking.contact,
                  firstName: guestForm.firstName,
                  lastName: guestForm.lastName,
                })
                setContact({
                  ...contact,
                  firstName: guestForm.firstName,
                  lastName: guestForm.lastName,
                })
                pushToast('Данные гостей обновлены')
                setModal(null)
              })
            }}
          >
            Сохранить
          </Button>
        </div>
      </Modal>

      <Modal open={modal === 'contact'} title="Связаться с объектом" onClose={() => setModal(null)}>
        <div className="space-y-3">
          <p className="text-sm">Ресепшен: +90 242 000 00 00</p>
          <p className="text-sm">Email: stay@{hotel.id}.demo</p>
          <label className="block text-sm font-medium">
            Сообщение
            <textarea
              className="mt-1.5 min-h-24 w-full rounded-2xl border border-border px-3 py-2"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </label>
          <Button
            fullWidth
            onClick={() => {
              pushToast('Сообщение отправлено')
              setMessage('')
              setModal(null)
            }}
          >
            Отправить
          </Button>
        </div>
      </Modal>

      <Modal open={modal === 'cancel'} title="Условия отмены" onClose={() => setModal(null)}>
        <p>Бесплатная отмена до 18:00 12 июня. После этого удерживается стоимость первых суток.</p>
      </Modal>

      <Modal open={modal === 'download'} title="Подтверждение" onClose={() => setModal(null)}>
        <p className="mb-3">Файл подтверждения бронирования {booking.id} готов.</p>
        <Button
          fullWidth
          onClick={() => {
            const blob = new Blob(
              [
                `О!Хочу\nБронь ${booking.id}\n${hotel.name}\n${formatDateRu(booking.checkIn)} - ${formatDateRu(booking.checkOut)}\nСумма ${formatPrice(booking.totalPrice)} RUB`,
              ],
              { type: 'text/plain;charset=utf-8' },
            )
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${booking.id}.txt`
            a.click()
            URL.revokeObjectURL(url)
            setModal(null)
          }}
        >
          Скачать .txt
        </Button>
      </Modal>
    </main>
  )
}
