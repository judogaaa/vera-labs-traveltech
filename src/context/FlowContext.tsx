import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { Booking, Trip, UserContact } from '../types/booking'
import type { Hotel, Room } from '../types/hotel'
import type { HotelMatch, MatchScenario, VisualAnalysis } from '../types/vision'
import type { VisualSearchInput } from '../types/visualSearch'
import type { AuthSession } from '../services/authService'
import * as authService from '../services/authService'
import { setMatchScenario as setVisionScenario } from '../services/visionService'
import { readStorage, writeStorage, STORAGE_KEYS } from '../lib/storage'
import { Toast } from '../components/Toast'
import { revokeObjectUrl } from '../utils/objectUrl'

export type UploadedImage = {
  file: File
  previewUrl: string
  name: string
  size: number
}

type FlowContextValue = {
  uploaded: UploadedImage | null
  setUploaded: (value: UploadedImage | null) => void
  clearUploaded: () => void
  visualSearch: VisualSearchInput | null
  setVisualSearch: (value: VisualSearchInput | null) => void
  clearVisualSearch: () => void
  analysis: VisualAnalysis | null
  setAnalysis: (value: VisualAnalysis | null) => void
  matches: HotelMatch[]
  setMatches: (value: HotelMatch[]) => void
  selectedHotel: Hotel | null
  setSelectedHotel: (hotel: Hotel | null) => void
  selectedRoom: Room | null
  setSelectedRoom: (room: Room | null) => void
  bookings: Booking[]
  booking: Booking | null
  setBooking: (booking: Booking | null) => void
  addBooking: (booking: Booking) => void
  updateBookingGuest: (bookingId: string, contact: UserContact) => void
  trip: Trip | null
  setTrip: (trip: Trip | null) => void
  contact: UserContact
  setContact: (contact: UserContact) => void
  checkIn: string
  checkOut: string
  setCheckIn: (value: string) => void
  setCheckOut: (value: string) => void
  guests: number
  setGuests: (n: number) => void
  scenario: MatchScenario
  setScenario: (scenario: MatchScenario) => void
  favorites: string[]
  toggleFavorite: (hotelId: string) => void
  session: AuthSession | null
  setSession: (session: AuthSession | null) => void
  logout: () => void
  pushToast: (message: string) => void
  authOpen: boolean
  setAuthOpen: (open: boolean) => void
}

const defaultContact: UserContact = {
  firstName: 'Анна',
  lastName: 'Иванова',
  email: 'anna@example.com',
  phone: '+7 000 000-00-00',
}

const FlowContext = createContext<FlowContextValue | null>(null)

export function FlowProvider({ children }: { children: ReactNode }) {
  const [uploaded, setUploadedState] = useState<UploadedImage | null>(null)
  const [visualSearch, setVisualSearchState] = useState<VisualSearchInput | null>(null)
  const [analysis, setAnalysis] = useState<VisualAnalysis | null>(null)
  const [matches, setMatches] = useState<HotelMatch[]>([])
  const [selectedHotel, setSelectedHotel] = useState<Hotel | null>(null)
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null)
  const [bookings, setBookings] = useState<Booking[]>(() =>
    readStorage<Booking[]>(STORAGE_KEYS.bookings, []),
  )
  const [booking, setBooking] = useState<Booking | null>(null)
  const [trip, setTrip] = useState<Trip | null>(null)
  const [contact, setContact] = useState<UserContact>(defaultContact)
  const [checkIn, setCheckIn] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 14)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
  const [checkOut, setCheckOut] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 21)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  })
  const [guests, setGuests] = useState(2)
  const [scenario, setScenarioState] = useState<MatchScenario>('exact')
  const [favorites, setFavorites] = useState<string[]>(() =>
    readStorage<string[]>(STORAGE_KEYS.favorites, []),
  )
  const [session, setSessionState] = useState<AuthSession | null>(() => authService.getSession())
  const [toast, setToast] = useState('')
  const [authOpen, setAuthOpen] = useState(false)

  useEffect(() => {
    writeStorage(STORAGE_KEYS.favorites, favorites)
  }, [favorites])

  useEffect(() => {
    writeStorage(STORAGE_KEYS.bookings, bookings)
  }, [bookings])

  const setUploaded = useCallback((value: UploadedImage | null) => {
    setUploadedState((prev) => {
      if (prev?.previewUrl) revokeObjectUrl(prev.previewUrl)
      return value
    })
    setVisualSearchState((prev) => {
      if (prev?.cropPreviewUrl) revokeObjectUrl(prev.cropPreviewUrl)
      return null
    })
    setAnalysis(null)
    setMatches([])
  }, [])

  const clearUploaded = useCallback(() => setUploaded(null), [setUploaded])

  const setVisualSearch = useCallback((value: VisualSearchInput | null) => {
    setVisualSearchState((prev) => {
      if (prev?.cropPreviewUrl && prev.cropPreviewUrl !== value?.cropPreviewUrl) {
        revokeObjectUrl(prev.cropPreviewUrl)
      }
      return value
    })
  }, [])

  const clearVisualSearch = useCallback(() => {
    setVisualSearchState((prev) => {
      if (prev?.cropPreviewUrl) revokeObjectUrl(prev.cropPreviewUrl)
      return null
    })
  }, [])

  const setScenario = useCallback((value: MatchScenario) => {
    setScenarioState(value)
    setVisionScenario(value)
  }, [])

  const toggleFavorite = useCallback((hotelId: string) => {
    setFavorites((prev) =>
      prev.includes(hotelId) ? prev.filter((id) => id !== hotelId) : [...prev, hotelId],
    )
  }, [])

  const setSession = useCallback((value: AuthSession | null) => {
    setSessionState(value)
    if (value) writeStorage(STORAGE_KEYS.auth, value)
  }, [])

  const logout = useCallback(() => {
    authService.logout()
    setSessionState(null)
    setToast('Вы вышли из аккаунта')
  }, [])

  const addBooking = useCallback((value: Booking) => {
    setBookings((prev) => [value, ...prev.filter((b) => b.id !== value.id)])
    setBooking(value)
  }, [])

  const updateBookingGuest = useCallback((bookingId: string, nextContact: UserContact) => {
    setBookings((prev) =>
      prev.map((item) => (item.id === bookingId ? { ...item, contact: nextContact } : item)),
    )
    setBooking((prev) => (prev?.id === bookingId ? { ...prev, contact: nextContact } : prev))
    setContact(nextContact)
  }, [])

  const pushToast = useCallback((message: string) => setToast(message), [])

  const value = useMemo<FlowContextValue>(
    () => ({
      uploaded,
      setUploaded,
      clearUploaded,
      visualSearch,
      setVisualSearch,
      clearVisualSearch,
      analysis,
      setAnalysis,
      matches,
      setMatches,
      selectedHotel,
      setSelectedHotel,
      selectedRoom,
      setSelectedRoom,
      bookings,
      booking,
      setBooking,
      addBooking,
      updateBookingGuest,
      trip,
      setTrip,
      contact,
      setContact,
      checkIn,
      checkOut,
      setCheckIn,
      setCheckOut,
      guests,
      setGuests,
      scenario,
      setScenario,
      favorites,
      toggleFavorite,
      session,
      setSession,
      logout,
      pushToast,
      authOpen,
      setAuthOpen,
    }),
    [
      uploaded,
      setUploaded,
      clearUploaded,
      visualSearch,
      setVisualSearch,
      clearVisualSearch,
      analysis,
      matches,
      selectedHotel,
      selectedRoom,
      bookings,
      booking,
      addBooking,
      updateBookingGuest,
      trip,
      contact,
      checkIn,
      checkOut,
      guests,
      scenario,
      setScenario,
      favorites,
      toggleFavorite,
      session,
      setSession,
      logout,
      pushToast,
      authOpen,
    ],
  )

  return (
    <FlowContext.Provider value={value}>
      {children}
      <Toast message={toast} open={Boolean(toast)} onClose={() => setToast('')} />
    </FlowContext.Provider>
  )
}

export function useFlow() {
  const ctx = useContext(FlowContext)
  if (!ctx) throw new Error('useFlow must be used within FlowProvider')
  return ctx
}
