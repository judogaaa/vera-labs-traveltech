export type Hotel = {
  id: string
  name: string
  city: string
  country: string
  address: string
  rating: number
  reviewCount: number
  pricePerNight: number
  images: string[]
  amenities: string[]
  description: string
  matchedFeatures: string[]
  visualTags?: string[]
  rooms: Room[]
}

export type Room = {
  id: string
  hotelId: string
  name: string
  area: number
  bed: string
  meal: string
  cancellation: string
  paymentTerms: string
  pricePerNight: number
  totalPrice: number
  nights: number
  image: string
}

export type SimilarHotel = {
  hotelId: string
  name: string
  city: string
  country: string
  rating: number
  reviewCount: number
  pricePerNight: number
  savings: number
  image: string
  features: string[]
}
