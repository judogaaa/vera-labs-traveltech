import { lazy, Suspense } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { HomeScreen } from '../screens/HomeScreen'
// Eager: hotel + checkout are on the booking critical path; lazy deferral made cold
// /hotel/:id pay full transform cost on first navigation (measured on Windows Vite 8).
import { HotelDetailScreen } from '../screens/HotelDetailScreen'
import { CheckoutScreen } from '../screens/CheckoutScreen'
import { MotionPage } from '../motion/MotionPage'
import { useMotionProfile } from '../motion/useMotionProfile'
import { springs } from '../motion/tokens'

const CatalogScreen = lazy(() =>
  import('../screens/CatalogScreen').then((m) => ({ default: m.CatalogScreen })),
)
const UploadPreviewScreen = lazy(() =>
  import('../screens/UploadPreviewScreen').then((m) => ({ default: m.UploadPreviewScreen })),
)
const AnalysisScreen = lazy(() =>
  import('../screens/AnalysisScreen').then((m) => ({ default: m.AnalysisScreen })),
)
const MatchResultScreen = lazy(() =>
  import('../screens/MatchResultScreen').then((m) => ({ default: m.MatchResultScreen })),
)
const MultipleMatchesScreen = lazy(() =>
  import('../screens/MultipleMatchesScreen').then((m) => ({ default: m.MultipleMatchesScreen })),
)
const NoExactMatchScreen = lazy(() =>
  import('../screens/NoExactMatchScreen').then((m) => ({ default: m.NoExactMatchScreen })),
)
const PaymentSuccessScreen = lazy(() =>
  import('../screens/PaymentSuccessScreen').then((m) => ({ default: m.PaymentSuccessScreen })),
)
const TripsScreen = lazy(() =>
  import('../screens/MyTripScreen').then((m) => ({ default: m.TripsScreen })),
)
const MyTripScreen = lazy(() =>
  import('../screens/MyTripScreen').then((m) => ({ default: m.MyTripScreen })),
)
const FavoritesScreen = lazy(() =>
  import('../screens/FavoritesScreen').then((m) => ({ default: m.FavoritesScreen })),
)
const OhRouteScreen = lazy(() =>
  import('../screens/OhRouteScreen').then((m) => ({ default: m.OhRouteScreen })),
)
const HotelIntelligenceScreen = lazy(() =>
  import('../screens/HotelIntelligenceScreen').then((m) => ({ default: m.HotelIntelligenceScreen })),
)
const HotelIntelligenceDetailScreen = lazy(() =>
  import('../screens/HotelIntelligenceDetailScreen').then((m) => ({
    default: m.HotelIntelligenceDetailScreen,
  })),
)
const HotelierCabinetScreen = lazy(() =>
  import('../screens/HotelierCabinetScreen').then((m) => ({ default: m.HotelierCabinetScreen })),
)
const CompareHotelsScreen = lazy(() =>
  import('../screens/CompareHotelsScreen').then((m) => ({ default: m.CompareHotelsScreen })),
)
const NotFoundScreen = lazy(() =>
  import('../screens/NotFoundScreen').then((m) => ({ default: m.NotFoundScreen })),
)

function RouteFallback() {
  const profile = useMotionProfile()
  return (
    <motion.div
      className="flex min-h-[40vh] items-center justify-center"
      aria-busy="true"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={profile.reduce ? { duration: 0.12 } : springs.gentle}
    >
      <div className="flex flex-col items-center gap-3 text-sm text-text-muted">
        <motion.span
          className="h-8 w-8 rounded-full border-2 border-brand-green-400 border-t-brand-blue-950"
          animate={profile.reduce ? undefined : { rotate: 360 }}
          transition={profile.reduce ? undefined : { duration: 0.9, repeat: Infinity, ease: 'linear' }}
          aria-hidden
        />
        <span>Загрузка…</span>
      </div>
    </motion.div>
  )
}

export function AppRouter() {
  const location = useLocation()

  return (
    <AnimatePresence mode="wait" initial={false}>
      <MotionPage key={location.pathname}>
        <Suspense fallback={<RouteFallback />}>
          <Routes location={location}>
            <Route path="/" element={<HomeScreen />} />
            <Route path="/catalog" element={<CatalogScreen />} />
            <Route path="/search/preview" element={<UploadPreviewScreen />} />
            <Route path="/search/analyzing" element={<AnalysisScreen />} />
            <Route path="/search/result" element={<MatchResultScreen />} />
            <Route path="/search/matches" element={<MultipleMatchesScreen />} />
            <Route path="/search/no-match" element={<NoExactMatchScreen />} />
            <Route path="/hotel/:hotelId" element={<HotelDetailScreen />} />
            <Route path="/checkout/:hotelId/:roomId" element={<CheckoutScreen />} />
            <Route path="/booking/success/:bookingId" element={<PaymentSuccessScreen />} />
            <Route path="/trips" element={<TripsScreen />} />
            <Route path="/trips/:bookingId" element={<MyTripScreen />} />
            <Route path="/favorites" element={<FavoritesScreen />} />
            <Route path="/oh-route" element={<OhRouteScreen />} />
            <Route path="/hotel-intelligence" element={<HotelIntelligenceScreen />} />
            <Route
              path="/hotel-intelligence/hotel/:hotelId"
              element={<HotelIntelligenceDetailScreen />}
            />
            <Route path="/hotel-intelligence/hotelier" element={<HotelierCabinetScreen />} />
            <Route path="/hotel-intelligence/compare" element={<CompareHotelsScreen />} />

            <Route path="/upload" element={<Navigate to="/search/preview" replace />} />
            <Route path="/analysis" element={<Navigate to="/search/analyzing" replace />} />
            <Route path="/result" element={<Navigate to="/search/result" replace />} />
            <Route path="/matches" element={<Navigate to="/search/matches" replace />} />
            <Route path="/no-match" element={<Navigate to="/search/no-match" replace />} />
            <Route path="/checkout" element={<Navigate to="/" replace />} />
            <Route path="/success" element={<Navigate to="/trips" replace />} />
            <Route path="/trip" element={<Navigate to="/oh-route" replace />} />

            <Route path="*" element={<NotFoundScreen />} />
          </Routes>
        </Suspense>
      </MotionPage>
    </AnimatePresence>
  )
}
