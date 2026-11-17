import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { DayPlan, HotelTripContext, PlannedTrip, TripStop } from '../../types/trip'
import { tripVerifiedSegmentLines } from '../../lib/tripRouteLine'

type Props = {
  trip: PlannedTrip | null
  day: DayPlan | null
  selectedStopId: string | null
  onSelectStop: (stopId: string) => void
}

// Free vector tiles, no API key. Label language is forced at runtime:
// name:ru → name:en → name (see applyRussianLabels).
const VECTOR_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty'
const ROUTE_SOURCE_ID = 'trip-route'
const ROUTE_LAYER_ID = 'trip-route-line'
const MODE_LINE_COLOR: Record<string, string> = {
  walk: '#1c286e',
  car: '#0e174d',
  transit: '#3d5a80',
}

function hotelPoint(hotel: HotelTripContext | undefined): [number, number] | null {
  if (hotel?.lat != null && hotel?.lon != null) return [hotel.lon, hotel.lat]
  return null
}

function emptyRouteCollection() {
  return { type: 'FeatureCollection' as const, features: [] as never[] }
}

/** Prefer Russian labels, then English, then the local name. */
function applyRussianLabels(map: maplibregl.Map) {
  try {
    const style = map.getStyle()
    for (const layer of style.layers ?? []) {
      if (layer.type !== 'symbol') continue
      const layout = (layer as { layout?: Record<string, unknown> }).layout
      if (!layout || !('text-field' in layout)) continue
      map.setLayoutProperty(layer.id, 'text-field', [
        'coalesce',
        ['get', 'name:ru'],
        ['get', 'name:en'],
        ['get', 'name'],
      ])
    }
  } catch {
    // Label override is best-effort; the map stays usable in local names.
  }
}

export function TripMap({ trip, day, selectedStopId, onSelectStop }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markersRef = useRef<Map<string, maplibregl.Marker>>(new Map())
  const markersSigRef = useRef('')
  const boundsSigRef = useRef('')
  const labelsAppliedRef = useRef(false)
  const onSelectRef = useRef(onSelectStop)

  useEffect(() => {
    onSelectRef.current = onSelectStop
  }, [onSelectStop])

  // Map is created exactly once; destroyed only on real unmount.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: VECTOR_STYLE_URL,
      center: [37.6, 55.75],
      zoom: 3,
      attributionControl: {},
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('error', () => {
      // Tile/network hiccups must not crash the page (no unhandled errors).
    })
    const applyLabels = () => {
      if (labelsAppliedRef.current) return
      labelsAppliedRef.current = true
      applyRussianLabels(map)
    }
    if (map.isStyleLoaded()) applyLabels()
    else map.once('load', applyLabels)
    mapRef.current = map
    const markers = markersRef.current
    return () => {
      markers.forEach((m) => m.remove())
      markers.clear()
      markersSigRef.current = ''
      boundsSigRef.current = ''
      labelsAppliedRef.current = false
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !trip) return

    const stops: TripStop[] = day?.stops ?? trip.days.flatMap((d) => d.stops)
    const hp = hotelPoint(trip.hotel)

    const draw = () => {
      const m = mapRef.current
      if (!m) return

      // --- Route via setData (no removeLayer/addLayer churn) ---
      // Mixed walk+car days have null day.route.polyline — draw each verified leg.
      // Never connect stops with straight lines when OSRM geometry is missing.
      const lines = tripVerifiedSegmentLines({
        segments: day?.segments,
        routePolyline: day?.route.polyline,
        routeVerified: day?.route.verified,
      })
      const coords = lines.flatMap((l) => l.coordinates)

      if (!m.getSource(ROUTE_SOURCE_ID)) {
        m.addSource(ROUTE_SOURCE_ID, { type: 'geojson', data: emptyRouteCollection() })
        m.addLayer({
          id: ROUTE_LAYER_ID,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          paint: {
            'line-color': [
              'match',
              ['get', 'mode'],
              'car',
              MODE_LINE_COLOR.car,
              'transit',
              MODE_LINE_COLOR.transit,
              MODE_LINE_COLOR.walk,
            ],
            'line-width': ['match', ['get', 'mode'], 'car', 4, 3.5],
            'line-opacity': 0.88,
          },
        })
      }
      const src = m.getSource(ROUTE_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
      if (lines.length > 0) {
        src?.setData({
          type: 'FeatureCollection',
          features: lines.map((line) => ({
            type: 'Feature' as const,
            properties: { mode: line.mode },
            geometry: { type: 'LineString' as const, coordinates: line.coordinates },
          })),
        })
        if (m.getLayer(ROUTE_LAYER_ID)) m.setLayoutProperty(ROUTE_LAYER_ID, 'visibility', 'visible')
      } else {
        src?.setData(emptyRouteCollection())
        if (m.getLayer(ROUTE_LAYER_ID)) m.setLayoutProperty(ROUTE_LAYER_ID, 'visibility', 'none')
      }

      // --- Markers: rebuild only when stops/selection actually changed ---
      const sig = JSON.stringify([
        hp,
        stops.map((s) => [s.id, s.lat, s.lon, s.name] as const),
        selectedStopId,
      ])
      if (sig !== markersSigRef.current) {
        markersSigRef.current = sig
        markersRef.current.forEach((marker) => marker.remove())
        markersRef.current.clear()

        if (hp) {
          const el = document.createElement('div')
          el.className = 'oh-map-hotel'
          el.title = trip.hotel.name || 'Отель'
          el.innerHTML = '<span>Отель</span>'
          const marker = new maplibregl.Marker({ element: el }).setLngLat(hp).addTo(m)
          markersRef.current.set('hotel', marker)
        }
        stops.forEach((stop, idx) => {
          const el = document.createElement('button')
          el.type = 'button'
          el.className = `oh-map-stop${selectedStopId === stop.id ? ' is-selected' : ''}`
          el.textContent = String(idx + 1)
          el.title = stop.name
          el.addEventListener('click', () => onSelectRef.current(stop.id))
          const marker = new maplibregl.Marker({ element: el })
            .setLngLat([stop.lon, stop.lat])
            .addTo(m)
          markersRef.current.set(stop.id, marker)
        })
      }

      // --- Camera: fit only when the point set changed ---
      const boundsSig = JSON.stringify([hp, stops.map((s) => [s.lat, s.lon]), coords.length])
      if (boundsSig !== boundsSigRef.current) {
        boundsSigRef.current = boundsSig
        const bounds = new maplibregl.LngLatBounds()
        if (hp) bounds.extend(hp)
        stops.forEach((s) => bounds.extend([s.lon, s.lat]))
        coords.forEach((c) => bounds.extend(c))
        if (!bounds.isEmpty()) {
          m.fitBounds(bounds, { padding: 56, maxZoom: 14, duration: 600 })
        }
      }
    }

    if (map.isStyleLoaded()) draw()
    else map.once('load', draw)
  }, [trip, day, selectedStopId])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !trip || !selectedStopId) return
    const stop = (day?.stops ?? trip.days.flatMap((d) => d.stops)).find((s) => s.id === selectedStopId)
    if (!stop) return
    map.easeTo({ center: [stop.lon, stop.lat], zoom: Math.max(map.getZoom(), 13), duration: 450 })
  }, [selectedStopId, day, trip])

  return (
    <div className="relative h-full min-h-[280px] w-full overflow-hidden rounded-[20px] border border-border bg-surface-muted">
      <div ref={containerRef} className="h-full w-full" />
      {!trip ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/55 px-6 text-center">
          <p className="max-w-sm text-sm text-text-secondary">
            Карта откроется, когда появятся подтверждённые места маршрута
          </p>
        </div>
      ) : null}
    </div>
  )
}
