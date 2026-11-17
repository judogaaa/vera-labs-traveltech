import { useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { motion, useReducedMotion } from 'framer-motion'
import { Button } from '../components/Button'
import { TripSummary } from '../components/TripSummary'
import { EmptyState } from '../components/EmptyState'
import { PageEnter } from '../components/PageEnter'
import { useFlow } from '../context/FlowContext'
import { formatDateRu, getHotelById } from '../data/hotels'

export function PaymentSuccessScreen() {
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const { bookingId = '' } = useParams()
  const { selectedHotel, selectedRoom, bookings, guests } = useFlow()

  const booking = bookings.find((b) => b.id === bookingId) ?? null
  const hotel = selectedHotel ?? (booking ? getHotelById(booking.hotelId) : null)
  const room =
    selectedRoom ??
    hotel?.rooms.find((item) => item.id === booking?.roomId) ??
    null

  if (!hotel || !room || !booking) {
    return (
      <main className="page-container py-10">
        <EmptyState
          title="Бронирование ещё не оформлено"
          description="Пройдите путь от поиска до оплаты, чтобы увидеть подтверждение."
          actionLabel="На главную"
          onAction={() => navigate('/')}
        />
      </main>
    )
  }

  return (
    <main className="page-container space-y-6 py-8 sm:py-10">
      <PageEnter>
        <div className="rounded-[24px] border border-success/20 bg-success-soft px-5 py-8 text-center sm:px-8">
          <motion.div
            className="mx-auto inline-flex"
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.86 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, scale: 1 }}
            transition={{ duration: 0.28, ease: 'easeOut' }}
          >
            <CheckCircle2 className="text-success" size={36} aria-hidden />
          </motion.div>
          <h1 className="mt-3 text-3xl font-bold text-brand-blue-950 sm:text-4xl">Бронирование подтверждено</h1>
          <p className="mx-auto mt-3 max-w-xl text-text-secondary">
            {hotel.name} ждёт вас {formatDateRu(booking.checkIn)} — {formatDateRu(booking.checkOut)}.
          </p>
        </div>
      </PageEnter>

      <PageEnter delay={0.06}>
        <TripSummary
          hotel={hotel}
          room={room}
          checkIn={formatDateRu(booking.checkIn)}
          checkOut={formatDateRu(booking.checkOut)}
          guests={guests}
          bookingId={booking.id}
          totalPrice={booking.totalPrice}
        />
      </PageEnter>

      <div className="flex flex-col gap-3 sm:max-w-md sm:flex-row">
        <Button fullWidth onClick={() => navigate(`/trips/${booking.id}`)}>
          Открыть мою поездку
        </Button>
        <Button variant="secondary" fullWidth onClick={() => navigate('/')}>
          На главную
        </Button>
      </div>
    </main>
  )
}
