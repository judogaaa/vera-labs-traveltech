export type CatalogHotel = {
  id: string
  name: string
  chain: string | null
  latitude: number | null
  longitude: number | null
  images: string[]
  provider: string
  image_count: number
  /** Present only for local demo / curated / region hotels */
  city?: string
  country?: string
  country_code?: string
  resort_area?: string
  rating?: number
  reviewCount?: number
  pricePerNight?: number
  amenities?: string[]
  description?: string
  price_status?: string
  source: 'hotels50k' | 'demo' | 'curated'
}
