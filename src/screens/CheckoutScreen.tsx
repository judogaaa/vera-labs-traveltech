import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { CheckoutSection } from '../components/CheckoutSection'
import { BrandedPaymentCard } from '../components/BrandedPaymentCard'
import { Input } from '../components/Input'
import { Checkbox } from '../components/Checkbox'
import { Button } from '../components/Button'
import { EmptyState } from '../components/EmptyState'
import { SafeImage } from '../components/SafeImage'
import { useFlow } from '../context/FlowContext'
import { createBooking } from '../services/bookingService'
import { formatDateRu, getHotelById, nightsBetween } from '../data/hotels'
import { formatPrice } from '../lib/format'
import { nextSelectedRoom, resolveCheckoutHotel } from '../lib/checkoutRoomSync'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

export function CheckoutScreen() {
  const navigate = useNavigate()
  const profile = useMotionProfile()
  const { hotelId = '', roomId = '' } = useParams()
  const {
    selectedHotel,
    selectedRoom,
    setSelectedHotel,
    setSelectedRoom,
    contact,
    setContact,
    guests,
    checkIn,
    checkOut,
    addBooking,
    setTrip,
  } = useFlow()

  // URL hotelId wins — never keep a stale selectedHotel from a previous card.
  const hotel = resolveCheckoutHotel(hotelId, selectedHotel, getHotelById)
  // Prefer route room from hotel catalog so context updates do not feed back into deps.
  const roomBase =
    hotel?.rooms.find((item) => item.id === roomId) ??
    (selectedRoom?.id === roomId && selectedRoom.hotelId === hotelId ? selectedRoom : null) ??
    null
  const room = roomBase

  const [agreed, setAgreed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [card, setCard] = useState({ number: '', expiry: '', cvc: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [focused, setFocused] = useState<string | null>(null)

  const nights = nightsBetween(checkIn, checkOut)
  const total = room ? room.pricePerNight * nights : 0
  const holderName = `${contact.firstName} ${contact.lastName}`.trim()

  useEffect(() => {
    if (hotel && selectedHotel?.id !== hotel.id) setSelectedHotel(hotel)
  }, [hotel, selectedHotel?.id, setSelectedHotel])

  useEffect(() => {
    const next = nextSelectedRoom(selectedRoom, roomBase, nights, total)
    if (next !== selectedRoom) setSelectedRoom(next)
  }, [roomBase, nights, total, selectedRoom, setSelectedRoom])

  const valid = useMemo(() => {
    return (
      Boolean(contact.firstName.trim()) &&
      Boolean(contact.lastName.trim()) &&
      contact.email.includes('@') &&
      contact.phone.trim().length >= 6 &&
      card.number.replace(/\s/g, '').length >= 12 &&
      /^\d{2}\/\d{2}$/.test(card.expiry) &&
      card.cvc.length >= 3 &&
      agreed
    )
  }, [contact, card, agreed])

  if (!hotel || !room) {
    return (
      <main className="page-container py-10">
        <EmptyState
          title="Сначала выберите номер"
          description="Откройте карточку отеля и выберите подходящий вариант."
          actionLabel="На главную"
          onAction={() => navigate('/')}
        />
      </main>
    )
  }

  const validate = () => {
    const next: Record<string, string> = {}
    if (!contact.firstName.trim()) next.firstName = 'Укажите имя'
    if (!contact.lastName.trim()) next.lastName = 'Укажите фамилию'
    if (!contact.email.includes('@')) next.email = 'Укажите корректный email'
    if (contact.phone.trim().length < 6) next.phone = 'Укажите телефон'
    if (card.number.replace(/\s/g, '').length < 12) next.number = 'Проверьте номер карты'
    if (!/^\d{2}\/\d{2}$/.test(card.expiry)) next.expiry = 'Формат ММ/ГГ'
    if (card.cvc.length < 3) next.cvc = 'Укажите CVC'
    if (!agreed) next.agreed = 'Нужно согласие с условиями'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const onSubmit = async () => {
    if (!validate()) return
    setLoading(true)
    try {
      // Demo booking only — card data never leaves the browser / is not persisted.
      const booking = await createBooking({
        hotelId: hotel.id,
        roomId: room.id,
        checkIn,
        checkOut,
        guests,
        contact,
        totalPrice: total,
      })
      addBooking(booking)
      setTrip({
        bookingId: booking.id,
        hotelId: booking.hotelId,
        roomId: booking.roomId,
        checkIn: booking.checkIn,
        checkOut: booking.checkOut,
        guests: booking.guests,
        guestNames: [`${booking.contact.firstName} ${booking.contact.lastName}`],
        totalPrice: `${formatPrice(booking.totalPrice)} ₽`,
        paymentStatus: 'Демо-оплата',
        cancellationDeadline: room.cancellation,
        checkInTime: 'с 14:00',
        documentsReady: true,
      })
      navigate(`/booking/success/${booking.id}`)
    } finally {
      setLoading(false)
    }
  }

  const formatPhone = (value: string) => {
    const digits = value.replace(/\D/g, '').slice(0, 11)
    if (!digits) return ''
    if (digits.length <= 1) return `+${digits}`
    if (digits.length <= 4) return `+${digits.slice(0, 1)} ${digits.slice(1)}`
    if (digits.length <= 7) return `+${digits.slice(0, 1)} ${digits.slice(1, 4)} ${digits.slice(4)}`
    return `+${digits.slice(0, 1)} ${digits.slice(1, 4)} ${digits.slice(4, 7)}-${digits.slice(7, 9)}-${digits.slice(9, 11)}`
  }

  const fieldRing = (name: string, hasError?: string) =>
    [
      'transition-[box-shadow,border-color] duration-200',
      hasError ? 'ring-2 ring-error/30' : focused === name ? 'ring-2 ring-brand-blue-700/25' : '',
    ]
      .filter(Boolean)
      .join(' ')

  return (
    <main className="page-container py-8 sm:py-10">
      <motion.div
        className="mb-7 max-w-2xl"
        initial={profile.reduce ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={springs.soft}
      >
        <p className="text-sm font-medium text-brand-blue-900">Оформление</p>
        <h1 className="mt-1 text-3xl font-bold tracking-[-0.02em] text-brand-blue-950 sm:text-4xl">
          Проверьте детали бронирования
        </h1>
        <p className="mt-2 text-text-secondary">
          Демо-оплата: средства не списываются. Для реальных платежей нужна интеграция с платёжным провайдером.
        </p>
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
        <div className="space-y-4 lg:col-span-7">
          <CheckoutSection title="Гости">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className={fieldRing('firstName', errors.firstName)}>
                <Input
                  label="Имя"
                  name="firstName"
                  autoComplete="given-name"
                  value={contact.firstName}
                  error={errors.firstName}
                  onFocus={() => setFocused('firstName')}
                  onBlur={() => setFocused(null)}
                  onChange={(e) => setContact({ ...contact, firstName: e.target.value })}
                />
              </div>
              <div className={fieldRing('lastName', errors.lastName)}>
                <Input
                  label="Фамилия"
                  name="lastName"
                  autoComplete="family-name"
                  value={contact.lastName}
                  error={errors.lastName}
                  onFocus={() => setFocused('lastName')}
                  onBlur={() => setFocused(null)}
                  onChange={(e) => setContact({ ...contact, lastName: e.target.value })}
                />
              </div>
            </div>
          </CheckoutSection>

          <CheckoutSection title="Контакты">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className={fieldRing('email', errors.email)}>
                <Input
                  label="Email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  value={contact.email}
                  error={errors.email}
                  onFocus={() => setFocused('email')}
                  onBlur={() => setFocused(null)}
                  onChange={(e) => setContact({ ...contact, email: e.target.value })}
                />
              </div>
              <div className={fieldRing('phone', errors.phone)}>
                <Input
                  label="Телефон"
                  name="phone"
                  type="tel"
                  autoComplete="tel"
                  value={contact.phone}
                  error={errors.phone}
                  onFocus={() => setFocused('phone')}
                  onBlur={() => setFocused(null)}
                  onChange={(e) => setContact({ ...contact, phone: formatPhone(e.target.value) })}
                />
              </div>
            </div>
          </CheckoutSection>

          <CheckoutSection title="Оплата (демо)">
            <div className="mb-5 max-w-md">
              <BrandedPaymentCard
                holderName={holderName}
                number={card.number}
                expiry={card.expiry}
                flipped={focused === 'cvc'}
                cvcLength={card.cvc}
              />
              <p className="mt-3 text-xs leading-5 text-text-muted">
                На карте — маскированный номер, имя и срок. При фокусе на CVC карта переворачивается; настоящий код не
                показывается и не сохраняется.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className={`sm:col-span-2 ${fieldRing('number', errors.number)}`}>
                <Input
                  label="Номер карты"
                  name="cardNumber"
                  autoComplete="cc-number"
                  inputMode="numeric"
                  placeholder="ACCT-000003"
                  value={card.number}
                  error={errors.number}
                  onFocus={() => setFocused('number')}
                  onBlur={() => setFocused(null)}
                  onChange={(e) => {
                    const digits = e.target.value.replace(/\D/g, '').slice(0, 16)
                    const grouped = digits.replace(/(\d{4})(?=\d)/g, '$1 ')
                    setCard({ ...card, number: grouped })
                  }}
                />
              </div>
              <div className={fieldRing('expiry', errors.expiry)}>
                <Input
                  label="Срок"
                  name="expiry"
                  autoComplete="cc-exp"
                  inputMode="numeric"
                  placeholder="ММ/ГГ"
                  value={card.expiry}
                  error={errors.expiry}
                  onFocus={() => setFocused('expiry')}
                  onBlur={() => setFocused(null)}
                  onChange={(e) => {
                    const digits = e.target.value.replace(/\D/g, '').slice(0, 4)
                    const next = digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits
                    setCard({ ...card, expiry: next })
                  }}
                />
              </div>
              <div className={fieldRing('cvc', errors.cvc)}>
                <Input
                  label="CVC"
                  name="cvc"
                  autoComplete="cc-csc"
                  inputMode="numeric"
                  value={card.cvc}
                  error={errors.cvc}
                  onFocus={() => setFocused('cvc')}
                  onBlur={() => setFocused(null)}
                  onChange={(e) => setCard({ ...card, cvc: e.target.value.replace(/\D/g, '').slice(0, 4) })}
                />
              </div>
            </div>
            <div className="mt-4 flex gap-2 text-xs font-semibold text-text-muted">
              <span className="rounded-lg border border-border px-2 py-1">VISA</span>
              <span className="rounded-lg border border-border px-2 py-1">MC</span>
              <span className="rounded-lg border border-border px-2 py-1">MIR</span>
            </div>
          </CheckoutSection>
        </div>

        <div className="lg:col-span-5">
          <aside className="overflow-hidden rounded-[24px] border border-border bg-white shadow-[0_16px_40px_-24px_rgba(14,23,77,0.35)] lg:sticky lg:top-24">
            <SafeImage src={hotel.images[0]} alt={hotel.name} className="aspect-[16/10]" eager />
            <div className="p-5 sm:p-6">
              <h2 className="text-lg font-bold text-brand-blue-950">{hotel.name}</h2>
              <p className="text-sm text-text-secondary">
                {hotel.city}, {hotel.country}
              </p>
              <p className="mt-1 text-sm font-medium text-text-primary">{room.name}</p>
              <dl className="mt-4 space-y-2.5 text-sm">
                <div className="flex justify-between gap-3">
                  <dt className="text-text-muted">Даты</dt>
                  <dd className="text-right font-medium">
                    {formatDateRu(checkIn)} — {formatDateRu(checkOut)}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-text-muted">Гости</dt>
                  <dd className="font-medium">{guests}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-text-muted">Отмена</dt>
                  <dd className="max-w-[62%] text-right font-medium leading-snug">{room.cancellation}</dd>
                </div>
                <div className="flex justify-between gap-3 border-t border-border pt-3">
                  <dt className="text-text-muted">
                    {formatPrice(room.pricePerNight)} ₽ × {nights}{' '}
                    {nights === 1 ? 'ночь' : nights < 5 ? 'ночи' : 'ночей'}
                  </dt>
                  <dd className="font-medium">{formatPrice(total)} ₽</dd>
                </div>
                <div className="flex justify-between gap-3 text-base">
                  <dt className="font-semibold">Итого</dt>
                  <dd className="font-bold text-brand-blue-950">{formatPrice(total)} ₽</dd>
                </div>
              </dl>
              <div className="mt-4">
                <Checkbox
                  label="Я согласен с условиями бронирования"
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                />
                {errors.agreed ? <p className="mt-1 text-sm text-error">{errors.agreed}</p> : null}
              </div>
              <div className="mt-4">
                <Button fullWidth disabled={!valid || loading} onClick={() => void onSubmit()}>
                  {loading ? 'Оформляем демо…' : `Демо-оплата ${formatPrice(total)} ₽`}
                </Button>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </main>
  )
}
