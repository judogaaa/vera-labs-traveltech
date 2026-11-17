/** Known demo / catalog coordinates for trip planner hotel context. */
const KNOWN: Record<string, { lat: number; lon: number }> = {
  'rixos-premium-tekirova': { lat: 36.5058, lon: 30.5284 },
  'akka-antedon': { lat: 36.862, lon: 30.74 },
}

export function resolveHotelCoords(
  hotelId: string,
  latitude?: number | null,
  longitude?: number | null,
): { lat: number; lon: number } | null {
  if (latitude != null && longitude != null && Number.isFinite(latitude) && Number.isFinite(longitude)) {
    return { lat: latitude, lon: longitude }
  }
  return KNOWN[hotelId] ?? null
}
