export function readStorage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function writeStorage<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore quota / private mode
  }
}

export function removeStorage(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // ignore
  }
}

export const STORAGE_KEYS = {
  auth: 'ohotchu.auth',
  favorites: 'ohotchu.favorites',
  bookings: 'ohotchu.bookings',
  lastSearch: 'ohotchu.lastSearch',
  plannedTrips: 'ohotchu.plannedTrips',
} as const
