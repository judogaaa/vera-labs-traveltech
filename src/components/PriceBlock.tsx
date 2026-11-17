import { formatPrice } from '../lib/format'

export function PriceBlock({
  pricePerNight,
  suffix = '/ ночь',
  prefix = 'от',
  large = false,
  priceStatus,
}: {
  pricePerNight?: number | null
  suffix?: string
  prefix?: string
  large?: boolean
  priceStatus?: string
}) {
  const hasPrice = pricePerNight != null && pricePerNight > 0
  if (!hasPrice) {
    return (
      <div className={large ? 'text-xl font-semibold text-text-secondary' : 'text-sm font-semibold text-text-secondary'}>
        Цена по запросу
      </div>
    )
  }
  const isEstimate = priceStatus === 'ui_estimate'
  const shownPrefix = isEstimate ? 'Ориентир' : prefix
  return (
    <div className={large ? 'text-2xl font-bold text-text-primary' : 'text-lg font-bold text-text-primary'}>
      {shownPrefix ? <span className="mr-1 text-sm font-medium text-text-secondary">{shownPrefix}</span> : null}
      {formatPrice(pricePerNight)} ₽
      <span className="ml-1 text-sm font-medium text-text-secondary">{suffix}</span>
      {isEstimate ? (
        <p className="mt-0.5 text-xs font-medium text-text-tertiary">не живой тариф API</p>
      ) : null}
    </div>
  )
}
