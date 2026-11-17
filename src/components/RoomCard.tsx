import type { Room } from '../types/hotel'
import { formatPrice } from '../lib/format'
import { Button } from './Button'
import { SafeImage } from './SafeImage'
import { MotionCard } from '../motion/MotionCard'

export function RoomCard({
  room,
  nights,
  onSelect,
  index = 0,
}: {
  room: Room
  nights: number
  onSelect: () => void
  index?: number
}) {
  const total = room.pricePerNight * nights

  return (
    <MotionCard
      index={index}
      className="overflow-hidden rounded-[20px] border border-border bg-white transition-[border-color,box-shadow] duration-200 hover:border-brand-green-400 hover:shadow-sm"
    >
      <div className="grid gap-0 md:grid-cols-[280px_1fr]">
        <SafeImage src={room.image} alt={room.name} className="min-h-[200px] md:min-h-full" />
        <div className="flex flex-col gap-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-xl font-bold text-brand-blue-950">{room.name}</h3>
              <p className="mt-1 text-sm text-text-secondary">
                {room.area} м² · {room.bed}
              </p>
            </div>
            <div className="text-right">
              <p className="text-xl font-bold text-text-primary">{formatPrice(room.pricePerNight)} ₽</p>
              <p className="text-sm text-text-secondary">за ночь</p>
            </div>
          </div>
          <dl className="grid gap-2 text-sm text-text-secondary sm:grid-cols-2">
            <div>
              <dt className="text-text-muted">Питание</dt>
              <dd className="font-medium text-text-primary">{room.meal}</dd>
            </div>
            <div>
              <dt className="text-text-muted">Отмена</dt>
              <dd className="font-medium text-text-primary">{room.cancellation}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-text-muted">Оплата</dt>
              <dd className="font-medium text-text-primary">{room.paymentTerms}</dd>
            </div>
          </dl>
          <div className="mt-auto flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-text-secondary">
              Итого за {nights} ноч.: <span className="font-bold text-text-primary">{formatPrice(total)} ₽</span>
            </p>
            <Button className="sm:min-w-[160px]" onClick={onSelect}>
              Выбрать
            </Button>
          </div>
        </div>
      </div>
    </MotionCard>
  )
}
