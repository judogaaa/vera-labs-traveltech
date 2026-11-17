import type { Hotel, Room } from '../types/hotel'
import { formatPrice } from '../lib/format'
import { StatusBadge } from './StatusBadge'
import { SafeImage } from './SafeImage'

export function TripSummary({
  hotel,
  room,
  checkIn,
  checkOut,
  guests,
  bookingId,
  totalPrice,
  paymentStatus = 'Оплачено',
}: {
  hotel: Hotel
  room: Room
  checkIn: string
  checkOut: string
  guests: number
  bookingId?: string
  totalPrice: number
  paymentStatus?: string
}) {
  return (
    <div className="overflow-hidden rounded-[22px] border border-border bg-white">
      <SafeImage src={hotel.images[0]} alt={hotel.name} className="aspect-[16/9] sm:aspect-[21/9]" />
      <div className="space-y-3 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-xl font-bold text-brand-blue-950">{hotel.name}</h3>
            <p className="text-sm text-text-secondary">
              {hotel.city}, {hotel.country}
            </p>
          </div>
          <StatusBadge>{paymentStatus}</StatusBadge>
        </div>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-text-muted">Даты</dt>
            <dd className="font-medium text-text-primary">
              {checkIn} — {checkOut}
            </dd>
          </div>
          <div>
            <dt className="text-text-muted">Гости</dt>
            <dd className="font-medium text-text-primary">{guests}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Номер</dt>
            <dd className="font-medium text-text-primary">{room.name}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Сумма</dt>
            <dd className="font-medium text-text-primary">{formatPrice(totalPrice)} ₽</dd>
          </div>
          {bookingId ? (
            <div className="sm:col-span-2">
              <dt className="text-text-muted">Номер брони</dt>
              <dd className="font-medium text-text-primary">{bookingId}</dd>
            </div>
          ) : null}
        </dl>
      </div>
    </div>
  )
}
