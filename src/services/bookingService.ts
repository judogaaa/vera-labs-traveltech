import type { Booking, Trip, UserContact } from '../types/booking'
import { getHotelById } from '../data/hotels'
import type { Hotel, Room } from '../types/hotel'
import { readStorage, writeStorage, STORAGE_KEYS } from '../lib/storage'

export type CreateBookingPayload = {
  hotelId: string
  roomId: string
  checkIn: string
  checkOut: string
  guests: number
  contact: UserContact
  totalPrice: number
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function formatRub(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value) + ' ₽'
}

export async function getHotel(id: string): Promise<Hotel | null> {
  await delay(80)
  return getHotelById(id) ?? null
}

export async function getRooms(hotelId: string): Promise<Room[]> {
  await delay(80)
  return getHotelById(hotelId)?.rooms ?? []
}

export async function createBooking(payload: CreateBookingPayload): Promise<Booking> {
  await delay(1000)
  const booking: Booking = {
    id: `OH-${Date.now().toString().slice(-8)}`,
    hotelId: payload.hotelId,
    roomId: payload.roomId,
    checkIn: payload.checkIn,
    checkOut: payload.checkOut,
    guests: payload.guests,
    totalPrice: payload.totalPrice,
    status: 'confirmed',
    contact: payload.contact,
    createdAt: new Date().toISOString(),
  }
  const existing = readStorage<Booking[]>(STORAGE_KEYS.bookings, [])
  writeStorage(STORAGE_KEYS.bookings, [booking, ...existing.filter((b) => b.id !== booking.id)])
  return booking
}

export async function getBookings(): Promise<Booking[]> {
  await delay(60)
  return readStorage<Booking[]>(STORAGE_KEYS.bookings, [])
}

export async function getBooking(bookingId: string): Promise<Booking | null> {
  await delay(60)
  return readStorage<Booking[]>(STORAGE_KEYS.bookings, []).find((b) => b.id === bookingId) ?? null
}

export async function getTrip(bookingId: string): Promise<Trip | null> {
  const booking = await getBooking(bookingId)
  if (!booking) return null
  return {
    bookingId: booking.id,
    hotelId: booking.hotelId,
    roomId: booking.roomId,
    checkIn: booking.checkIn,
    checkOut: booking.checkOut,
    guests: booking.guests,
    guestNames: [`${booking.contact.firstName} ${booking.contact.lastName}`],
    totalPrice: formatRub(booking.totalPrice),
    paymentStatus: 'Оплачено',
    cancellationDeadline: '12 июня, 18:00',
    checkInTime: 'с 14:00',
    documentsReady: true,
  }
}

export async function updateGuest(bookingId: string, contact: UserContact): Promise<Booking | null> {
  await delay(400)
  const list = readStorage<Booking[]>(STORAGE_KEYS.bookings, [])
  const next = list.map((item) => (item.id === bookingId ? { ...item, contact } : item))
  writeStorage(STORAGE_KEYS.bookings, next)
  return next.find((item) => item.id === bookingId) ?? null
}
