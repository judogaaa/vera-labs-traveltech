import { formatPrice } from '../lib/format'
import { AppleDatePicker } from './AppleDatePicker'
import { Button } from './Button'
import { GuestCountControl } from './GuestCountControl'

function todayIsoLocal(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const TODAY_ISO = todayIsoLocal()

export function BookingSidebar({
  pricePerNight,
  nights,
  guests,
  checkIn,
  checkOut,
  onCheckInChange,
  onCheckOutChange,
  onGuestsChange,
  onSelectRoom,
  priceStatus,
}: {
  pricePerNight?: number | null
  nights: number
  guests: number
  checkIn: string
  checkOut: string
  onCheckInChange: (value: string) => void
  onCheckOutChange: (value: string) => void
  onGuestsChange: (value: number) => void
  onSelectRoom: () => void
  priceStatus?: string
}) {
  const safeNights = Number.isFinite(nights) && nights > 0 ? nights : 1
  const hasPrice = pricePerNight != null && Number.isFinite(pricePerNight) && pricePerNight > 0
  const total = hasPrice ? pricePerNight * safeNights : 0
  const isEstimate = priceStatus === 'ui_estimate'

  return (
    <aside className="rounded-[24px] border border-border bg-white p-5 lg:sticky lg:top-24">
      <h2 className="text-lg font-bold text-brand-blue-950">Ваше проживание</h2>
      {hasPrice ? (
        <p className="mt-2 text-2xl font-bold text-brand-blue-950">
          {isEstimate ? (
            <span className="mr-1 text-sm font-medium text-text-secondary">Ориентир</span>
          ) : null}
          {formatPrice(pricePerNight)} ₽
          <span className="ml-1 text-sm font-medium text-text-secondary">/ ночь</span>
        </p>
      ) : (
        <p className="mt-2 text-lg font-semibold text-text-secondary">Цена по запросу</p>
      )}
      <div className="mt-5 grid grid-cols-2 gap-3">
        <AppleDatePicker
          label="Заезд"
          value={checkIn}
          min={TODAY_ISO}
          onChange={onCheckInChange}
        />
        <AppleDatePicker
          label="Выезд"
          value={checkOut}
          min={checkIn || TODAY_ISO}
          onChange={onCheckOutChange}
          align="end"
        />
      </div>
      <div className="mt-3">
        <GuestCountControl value={guests} onChange={onGuestsChange} />
      </div>
      {hasPrice ? (
        <div className="mt-5 space-y-2 border-t border-border pt-4 text-sm">
          <div className="flex justify-between text-text-secondary">
            <span>
              {formatPrice(pricePerNight)} ₽ × {safeNights} ноч.
            </span>
            <span>{formatPrice(total)} ₽</span>
          </div>
          <div className="flex justify-between text-base font-semibold text-text-primary">
            <span>Итого</span>
            <span>{formatPrice(total)} ₽</span>
          </div>
          {isEstimate ? (
            <p className="text-xs text-text-tertiary">Ориентир, не живой тариф API</p>
          ) : null}
        </div>
      ) : (
        <p className="mt-5 border-t border-border pt-4 text-sm text-text-secondary">
          Итого уточняется при бронировании
        </p>
      )}
      <div className="mt-5">
        <Button fullWidth onClick={onSelectRoom}>
          Выбрать номер
        </Button>
      </div>
    </aside>
  )
}
