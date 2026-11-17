import type { Hotel, Room } from '../types/hotel'

/** URL hotelId always wins over a stale selectedHotel from another card. */
export function resolveCheckoutHotel(
  hotelId: string,
  selectedHotel: Hotel | null,
  getById: (id: string) => Hotel | null | undefined,
): Hotel | null {
  const fromUrl = getById(hotelId) ?? null
  if (fromUrl) return fromUrl
  if (selectedHotel?.id === hotelId) return selectedHotel
  return null
}

/** Pure helper: avoid CheckoutScreen ↔ context feedback loops. */
export function nextSelectedRoom(
  current: Room | null,
  base: Room | null,
  nights: number,
  totalPrice: number,
): Room | null {
  if (!base) return current
  if (
    current &&
    current.id === base.id &&
    current.nights === nights &&
    current.totalPrice === totalPrice
  ) {
    return current
  }
  return { ...base, nights, totalPrice }
}
