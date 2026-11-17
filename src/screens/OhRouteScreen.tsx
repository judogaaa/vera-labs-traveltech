import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '../components/Button'
import { TripChat } from '../components/trip/TripChat'
import { TripMap } from '../components/trip/TripMap'
import { TripTimeline } from '../components/trip/TripTimeline'
import { readStorage, writeStorage, STORAGE_KEYS } from '../lib/storage'
import {
  chatTrip,
  fetchTripStatus,
  getTrip,
  planTripWithProgress,
  tripPdfUrl,
} from '../services/tripPlannerService'
import type { HotelTripContext, PlannedTrip, TripProgressStep } from '../types/trip'

type MobileTab = 'chat' | 'map' | 'trip'
type RightMode = 'map' | 'trip'

type ChatMsg = { role: 'user' | 'assistant' | 'system'; content: string }

function loadSavedTrips(): PlannedTrip[] {
  return readStorage<PlannedTrip[]>(STORAGE_KEYS.plannedTrips, [])
}

function persistTrip(trip: PlannedTrip) {
  const list = loadSavedTrips().filter((t) => t.id !== trip.id)
  list.unshift(trip)
  writeStorage(STORAGE_KEYS.plannedTrips, list.slice(0, 30))
}

export function OhRouteScreen() {
  const [params] = useSearchParams()
  const hotelCtx = useMemo<HotelTripContext | null>(() => {
    const hotelId = params.get('hotelId')
    const name = params.get('hotelName')
    const lat = params.get('lat')
    const lon = params.get('lon')
    const city = params.get('city')
    const country = params.get('country')
    if (!hotelId && !name && !city) return null
    return {
      hotelId,
      name,
      lat: lat != null ? Number(lat) : null,
      lon: lon != null ? Number(lon) : null,
      city,
      country,
    }
  }, [params])

  const [trip, setTrip] = useState<PlannedTrip | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<TripProgressStep | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rightMode, setRightMode] = useState<RightMode>('map')
  const [mobileTab, setMobileTab] = useState<MobileTab>('chat')
  const [activeDay, setActiveDay] = useState(1)
  const [selectedStopId, setSelectedStopId] = useState<string | null>(null)
  const [devInfo, setDevInfo] = useState<Record<string, unknown> | null>(null)
  const showDev = params.get('dev') === '1'

  useEffect(() => {
    const tripId = params.get('trip')
    if (tripId) {
      void getTrip(tripId)
        .then((t) => {
          setTrip(t)
          persistTrip(t)
          setMessages(
            (t.messages as ChatMsg[]).length
              ? (t.messages as ChatMsg[])
              : [{ role: 'assistant', content: t.summary }],
          )
        })
        .catch(() => {
          /* local only */
          const local = loadSavedTrips().find((t) => t.id === tripId)
          if (local) {
            setTrip(local)
            setMessages([{ role: 'assistant', content: local.summary }])
          }
        })
    }
  }, [params])

  useEffect(() => {
    if (hotelCtx?.name) {
      setMessages([
        {
          role: 'system',
          content: `Вы выбрали «${hotelCtx.name}». Что хотите посмотреть рядом?`,
        },
      ])
    } else if (!params.get('trip')) {
      setMessages([
        {
          role: 'assistant',
          content:
            'Я О!Маршрут. Напишите город и сколько дней — соберу маршрут из реальных мест и покажу на карте.',
        },
      ])
    }
  }, [hotelCtx?.name, params])

  useEffect(() => {
    if (!showDev) return
    void fetchTripStatus()
      .then(setDevInfo)
      .catch(() => setDevInfo({ ok: false }))
  }, [showDev, trip?.id])

  const day = trip?.days.find((d) => d.dayNumber === activeDay) ?? trip?.days[0] ?? null

  const suggestions = hotelCtx
    ? [
        'Что посмотреть рядом',
        'Маршрут на 1 день',
        'Маршрут с ребёнком',
        'Пляжи и рестораны',
        'Главные достопримечательности',
      ]
    : [
        'Казань на 1 день, главные достопримечательности',
        'Анталья на 2 дня: пляж, старый город, рестораны',
        'Дубай на 2 дня с ребёнком, без долгих переездов',
      ]

  const send = async (text: string) => {
    setError(null)
    setMessages((m) => [...m, { role: 'user', content: text }])
    setBusy(true)
    setProgress('Понимаю пожелания')
    try {
      let next: PlannedTrip
      if (trip) {
        // staged progress for chat edits
        setProgress('Обновляю маршрут')
        next = await chatTrip(trip.id, text)
      } else {
        next = await planTripWithProgress(text, hotelCtx, setProgress)
      }
      setTrip(next)
      persistTrip(next)
      setMessages((m) => [...m, { role: 'assistant', content: next.summary || 'Маршрут готов' }])
      setActiveDay(1)
      setSelectedStopId(next.days[0]?.stops[0]?.id ?? null)
      setRightMode('map')
      if (window.matchMedia('(max-width: 1023px)').matches) setMobileTab('map')
    } catch (e) {
      const err = e as { message?: string; code?: string }
      const msg = err.message || 'Не удалось построить маршрут'
      setError(msg)
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: `Не удалось построить маршрут: ${msg}`,
        },
      ])
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  const panel = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-3 flex items-center gap-2 rounded-2xl bg-surface-muted p-1">
        {(['map', 'trip'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            onClick={() => setRightMode(mode)}
            className={`flex-1 rounded-xl px-3 py-2 text-sm font-semibold transition-colors ${
              rightMode === mode
                ? 'bg-white text-brand-blue-950 shadow-sm'
                : 'text-text-secondary hover:text-brand-blue-950'
            }`}
          >
            {mode === 'map' ? 'Карта' : 'Поездка'}
          </button>
        ))}
      </div>

      {rightMode === 'map' ? (
        <div className="min-h-0 flex-1">
          <TripMap
            trip={trip}
            day={day}
            selectedStopId={selectedStopId}
            onSelectStop={setSelectedStopId}
          />
        </div>
      ) : (
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
          <div>
            <h2 className="text-xl font-bold text-brand-blue-950">План поездки</h2>
            <p className="mt-1 text-sm text-text-secondary">{trip?.summary || 'Маршрут ещё не собран'}</p>
          </div>
          {trip ? (
            <>
              <div className="flex flex-wrap gap-2">
                {trip.days.map((d) => (
                  <button
                    key={d.dayNumber}
                    type="button"
                    onClick={() => setActiveDay(d.dayNumber)}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                      activeDay === d.dayNumber
                        ? 'bg-brand-blue-900 text-white'
                        : 'bg-white border border-border text-brand-blue-900'
                    }`}
                  >
                    День {d.dayNumber}
                  </button>
                ))}
              </div>
              {day ? (
                <TripTimeline day={day} selectedStopId={selectedStopId} onSelectStop={setSelectedStopId} />
              ) : null}
              <div className="flex flex-wrap gap-2 pb-2">
                <a href={tripPdfUrl(trip.id)} target="_blank" rel="noreferrer" className="no-underline">
                  <Button variant="secondary">Скачать поездку</Button>
                </a>
                <Button variant="soft" onClick={() => setRightMode('map')}>
                  Открыть на карте
                </Button>
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  )

  return (
    <main className="page-container flex min-h-[calc(100vh-68px)] flex-col py-4 sm:py-6">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-brand-blue-800">О!Маршрут</p>
          <h1 className="text-2xl font-bold text-brand-blue-950 sm:text-3xl">AI-планировщик поездки</h1>
          <p className="mt-1 max-w-xl text-sm text-text-secondary">
            Реальные места и маршруты через картографические провайдеры. Модель только помогает понять запрос.
          </p>
        </div>
        <Link to="/trips" className="text-sm font-semibold text-brand-blue-900 no-underline hover:underline">
          Мои поездки
        </Link>
      </div>

      {error ? (
        <div className="mb-3 rounded-2xl border border-error/30 bg-error-bg px-4 py-3 text-sm text-error">
          {error}
        </div>
      ) : null}

      {/* Mobile tabs */}
      <div className="mb-3 flex gap-1 rounded-2xl bg-surface-muted p-1 lg:hidden">
        {([
          ['chat', 'Чат'],
          ['map', 'Карта'],
          ['trip', 'Поездка'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              setMobileTab(id)
              if (id === 'map') setRightMode('map')
              if (id === 'trip') setRightMode('trip')
            }}
            className={`flex-1 rounded-xl px-3 py-2 text-sm font-semibold ${
              mobileTab === id ? 'bg-white text-brand-blue-950 shadow-sm' : 'text-text-secondary'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-12 lg:gap-5">
        <section
          className={`flex min-h-[420px] flex-col rounded-[24px] border border-border bg-surface-soft p-4 lg:col-span-5 lg:min-h-[640px] ${
            mobileTab === 'chat' ? 'flex' : 'hidden lg:flex'
          }`}
        >
          <TripChat
            messages={messages}
            busy={busy}
            progress={progress}
            suggestions={suggestions}
            onSend={(t) => void send(t)}
            placeholder={
              hotelCtx
                ? 'Например: маршрут на 1 день, пляж и ресторан'
                : 'Например: Казань на 1 день, главные достопримечательности'
            }
          />
        </section>

        <section
          className={`min-h-[420px] rounded-[24px] border border-border bg-white p-4 lg:col-span-7 lg:min-h-[640px] ${
            mobileTab === 'chat' ? 'hidden lg:block' : 'block'
          }`}
        >
          {panel}
        </section>
      </div>

      {showDev ? (
        <aside className="mt-4 rounded-2xl border border-border bg-white p-4 text-xs text-text-secondary">
          <p className="mb-2 font-semibold uppercase tracking-wide text-text-muted">О!Маршрут debug</p>
          <pre className="overflow-auto whitespace-pre-wrap">
            {JSON.stringify(
              {
                status: devInfo,
                tripDebug: trip?.debug ?? null,
                hotel: hotelCtx,
              },
              null,
              2,
            )}
          </pre>
        </aside>
      ) : null}
    </main>
  )
}
