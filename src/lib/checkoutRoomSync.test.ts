import { describe, expect, it } from 'vitest'
import { nextSelectedRoom, resolveCheckoutHotel } from './checkoutRoomSync'
import type { Hotel, Room } from '../types/hotel'

const base: Room = {
  id: 'r1',
  hotelId: 'h1',
  name: 'Standard',
  area: 20,
  bed: '1 king',
  meal: 'RO',
  cancellation: 'free',
  paymentTerms: 'demo',
  pricePerNight: 1000,
  totalPrice: 1000,
  nights: 1,
  image: '',
}

describe('resolveCheckoutHotel', () => {
  const hotelA = { id: 'a', name: 'A' } as Hotel
  const hotelB = { id: 'b', name: 'B' } as Hotel
  const getById = (id: string) => (id === 'a' ? hotelA : id === 'b' ? hotelB : null)

  it('prefers URL hotel over a different selectedHotel', () => {
    expect(resolveCheckoutHotel('b', hotelA, getById)?.id).toBe('b')
  })

  it('falls back to selectedHotel only when ids match', () => {
    expect(resolveCheckoutHotel('missing', hotelA, () => null)).toBeNull()
    expect(resolveCheckoutHotel('a', hotelA, () => null)?.id).toBe('a')
  })
})

describe('nextSelectedRoom', () => {
  it('returns same reference when id/nights/total already match (no loop)', () => {
    const current: Room = { ...base, nights: 3, totalPrice: 3000 }
    const next = nextSelectedRoom(current, base, 3, 3000)
    expect(next).toBe(current)
  })

  it('updates when nights or total change', () => {
    const current: Room = { ...base, nights: 2, totalPrice: 2000 }
    const next = nextSelectedRoom(current, base, 3, 3000)
    expect(next).not.toBe(current)
    expect(next?.nights).toBe(3)
    expect(next?.totalPrice).toBe(3000)
    expect(next?.id).toBe('r1')
  })

  it('creates selection from base when current is null', () => {
    const next = nextSelectedRoom(null, base, 1, 1000)
    expect(next).toEqual({ ...base, nights: 1, totalPrice: 1000 })
  })

  it('keeps current when base is missing', () => {
    const current: Room = { ...base, nights: 1, totalPrice: 1000 }
    expect(nextSelectedRoom(current, null, 1, 1000)).toBe(current)
  })
})
