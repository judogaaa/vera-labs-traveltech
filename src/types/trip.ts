export type TransportMode = 'walk' | 'car' | 'transit' | 'mixed'

export type HotelTripContext = {
  hotelId?: string | null
  name?: string | null
  lat?: number | null
  lon?: number | null
  city?: string | null
  country?: string | null
}

export type TravelSegment = {
  fromStopId: string
  toStopId: string
  mode: 'walk' | 'car' | 'transit'
  distanceMeters: number
  durationSeconds: number
  /** False when routing failed — never treat as a real km/min estimate. */
  verified?: boolean
  /** Encoded OSRM polyline (precision 5) for this leg; absent when unverified. */
  polyline?: string | null
}

export type TripStop = {
  id: string
  placeProvider: string
  placeId: string
  name: string
  category: string
  lat: number
  lon: number
  address: string
  startTime: string
  durationMinutes: number
  description: string
  photoUrl: string | null
  rating: number | null
  ratingCount: number | null
  website: string | null
  wikidataId?: string | null
}

export type DayPlan = {
  dayNumber: number
  date: string | null
  summary: string
  stops: TripStop[]
  segments: TravelSegment[]
  route: {
    distanceMeters: number
    durationSeconds: number
    polyline: string | null
    verified?: boolean
  }
  /** True when the day has no confirmed stops (incomplete multi-day pad). */
  incomplete?: boolean
}

export type PlannedTrip = {
  id: string
  destination: {
    name: string
    country: string
    lat: number
    lon: number
  }
  hotel: HotelTripContext
  days: DayPlan[]
  summary: string
  intent: Record<string, unknown>
  createdAt: string
  updatedAt: string
  messages: { role: string; content: string }[]
  debug: Record<string, unknown>
}

export type TripProgressStep =
  | 'Понимаю пожелания'
  | 'Ищу места'
  | 'Проверяю расстояния'
  | 'Собираю маршрут'
  | string
