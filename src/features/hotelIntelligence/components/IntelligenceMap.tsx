import { useEffect, useMemo, useRef, useState } from 'react'

export type MapHotelMarker = {
  id: string
  name: string
  lat: number
  lon: number
}

type Props = {
  hotels: MapHotelMarker[]
  selectedId?: string | null
  onSelect?: (hotelId: string) => void
  className?: string
}

type MapStatus = 'loading' | 'ready' | 'error' | 'idle'

/** Keyless public raster tiles (CartoCDN voyager now watermarks without API key). */
const TILE_TEMPLATES = [
  'https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
  'https://b.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
  'https://c.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
  'https://tile.openstreetmap.de/{z}/{x}/{y}.png',
]

const TILE_SIZE = 256
const ZOOM = 12

function lonToX(lon: number, zoom: number) {
  return ((lon + 180) / 360) * 2 ** zoom
}

function latToY(lat: number, zoom: number) {
  const rad = (lat * Math.PI) / 180
  return (
    ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * 2 ** zoom
  )
}

function tileUrl(z: number, x: number, y: number) {
  const tpl = TILE_TEMPLATES[(x + y) % TILE_TEMPLATES.length]
  return tpl.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y))
}

/**
 * DOM/img OSM-compatible raster map (no WebGL).
 * MapLibre left a blank grey pane in this product surface even when tiles
 * returned HTTP 200 — HTML tiles + markers are reliable for demo/screenshots.
 */
export function IntelligenceMap({ hotels, selectedId, onSelect, className }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 504, h: 420 })
  const [status, setStatus] = useState<MapStatus>('loading')
  const [tileError, setTileError] = useState(false)
  const [tilesOk, setTilesOk] = useState(0)
  const [tilesFail, setTilesFail] = useState(0)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.height > 0) setSize({ w: Math.round(r.width), h: Math.round(r.height) })
    }
    measure()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null
    ro?.observe(el)
    return () => ro?.disconnect()
  }, [])

  const center = useMemo(() => {
    if (!hotels.length) return { lat: 41.01, lon: 28.98 }
    if (selectedId) {
      const sel = hotels.find((h) => h.id === selectedId)
      if (sel) return { lat: sel.lat, lon: sel.lon }
    }
    const lat = hotels.reduce((s, h) => s + h.lat, 0) / hotels.length
    const lon = hotels.reduce((s, h) => s + h.lon, 0) / hotels.length
    return { lat, lon }
  }, [hotels, selectedId])

  const layout = useMemo(() => {
    const cx = lonToX(center.lon, ZOOM)
    const cy = latToY(center.lat, ZOOM)
    const originX = cx * TILE_SIZE - size.w / 2
    const originY = cy * TILE_SIZE - size.h / 2
    const x0 = Math.floor(originX / TILE_SIZE)
    const y0 = Math.floor(originY / TILE_SIZE)
    const cols = Math.ceil(size.w / TILE_SIZE) + 2
    const rows = Math.ceil(size.h / TILE_SIZE) + 2
    const tiles: { key: string; x: number; y: number; left: number; top: number; url: string }[] = []
    for (let iy = 0; iy < rows; iy++) {
      for (let ix = 0; ix < cols; ix++) {
        const tx = x0 + ix
        const ty = y0 + iy
        tiles.push({
          key: `${ZOOM}/${tx}/${ty}`,
          x: tx,
          y: ty,
          left: tx * TILE_SIZE - originX,
          top: ty * TILE_SIZE - originY,
          url: tileUrl(ZOOM, tx, ty),
        })
      }
    }
    const markers = hotels.map((h) => {
      const left = lonToX(h.lon, ZOOM) * TILE_SIZE - originX
      const top = latToY(h.lat, ZOOM) * TILE_SIZE - originY
      return { ...h, left, top }
    })
    return { tiles, markers }
  }, [center.lat, center.lon, hotels, size.h, size.w])

  useEffect(() => {
    setStatus('loading')
    setTilesOk(0)
    setTilesFail(0)
    setTileError(false)
  }, [center.lat, center.lon, size.w, size.h])

  useEffect(() => {
    if (tilesOk > 0) setStatus('ready')
    if (tilesFail > 0 && tilesOk === 0 && layout.tiles.length > 0) {
      // Wait until most attempted tiles failed
      if (tilesFail >= Math.min(4, layout.tiles.length)) {
        setTileError(true)
        setStatus('error')
      }
    }
  }, [tilesOk, tilesFail, layout.tiles.length])

  return (
    <div
      ref={wrapRef}
      className={[
        'relative min-h-[240px] overflow-hidden rounded-[22px] border border-border bg-surface-soft',
        className ?? 'h-[300px] w-full sm:h-[360px] lg:h-[420px]',
      ].join(' ')}
      role="region"
      aria-label="Карта отелей О!Подбор"
      data-testid="hi-map"
      data-map-status={status}
      data-map-tiles={tileError ? 'error' : tilesOk > 0 ? 'loaded' : 'pending'}
      data-marker-count={hotels.length}
    >
      <div className="absolute inset-0" data-testid="hi-map-canvas-host">
        {layout.tiles.map((t) => (
          <img
            key={t.key}
            src={t.url}
            alt=""
            width={TILE_SIZE}
            height={TILE_SIZE}
            draggable={false}
            className="pointer-events-none absolute max-w-none"
            style={{ left: t.left, top: t.top }}
            onLoad={() => setTilesOk((n) => n + 1)}
            onError={() => setTilesFail((n) => n + 1)}
          />
        ))}
        {layout.markers.map((m) => {
          const selected = m.id === selectedId
          return (
            <button
              key={m.id}
              type="button"
              data-hi-marker={m.id}
              aria-label={m.name}
              className="hi-map-marker absolute z-10 rounded-full border-2 border-white shadow"
              style={{
                left: m.left,
                top: m.top,
                width: selected ? 16 : 14,
                height: selected ? 16 : 14,
                transform: 'translate(-50%, -50%)',
                background: selected ? '#0e174d' : '#3d8b6e',
              }}
              onClick={() => onSelect?.(m.id)}
            />
          )
        })}
      </div>
      <p className="pointer-events-none absolute bottom-1 right-2 z-10 text-[9px] text-text-muted">
        © OpenStreetMap
      </p>
      {!hotels.length ? (
        <p className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-white/55 px-4 text-center text-sm text-text-secondary">
          Нет координат для отображения на карте
        </p>
      ) : null}
      {tileError && hotels.length > 0 ? (
        <div
          className="absolute inset-x-2 bottom-2 z-20 rounded-lg border border-border bg-white/95 px-3 py-2 text-center text-[11px] text-text-secondary shadow-sm"
          data-testid="hi-map-tile-error"
          role="status"
        >
          <p className="font-semibold text-brand-blue-950">Карта недоступна (тайлы не загрузились)</p>
          <p className="mt-0.5">Список отелей слева остаётся рабочим способом выбора.</p>
        </div>
      ) : null}
      {status === 'loading' && hotels.length > 0 && !tileError ? (
        <p className="pointer-events-none absolute left-2 top-2 z-10 rounded bg-white/80 px-2 py-0.5 text-[10px] text-text-muted">
          Загрузка карты…
        </p>
      ) : null}
    </div>
  )
}
