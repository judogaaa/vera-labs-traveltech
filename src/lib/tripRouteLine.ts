import { decodePolyline } from './polyline'

export type RouteLineMode = 'walk' | 'car' | 'transit'

export type VerifiedSegmentLine = {
  mode: RouteLineMode
  coordinates: [number, number][]
}

/**
 * Build map line coordinates for a day overview polyline.
 * Only a provider polyline with verified=true may be drawn —
 * never connect markers with straight-line guesses.
 */
export function tripRouteLineCoordinates(opts: {
  polyline?: string | null
  routeVerified?: boolean
}): [number, number][] {
  if (opts.routeVerified === false) return []
  const poly = opts.polyline?.trim()
  if (!poly) return []
  try {
    return decodePolyline(poly).map(([lat, lon]) => [lon, lat] as [number, number])
  } catch {
    return []
  }
}

type SegmentLike = {
  mode?: string | null
  verified?: boolean
  polyline?: string | null
}

/**
 * Prefer per-leg verified polylines (mixed walk+car days have no day.route.polyline).
 * Falls back to the day overview polyline only when it is verified.
 * Never invents straight chords between stops.
 */
export function tripVerifiedSegmentLines(opts: {
  segments?: SegmentLike[] | null
  routePolyline?: string | null
  routeVerified?: boolean
}): VerifiedSegmentLine[] {
  const lines: VerifiedSegmentLine[] = []
  for (const seg of opts.segments ?? []) {
    if (seg.verified === false) continue
    const poly = seg.polyline?.trim()
    if (!poly) continue
    try {
      const coordinates = decodePolyline(poly).map(
        ([lat, lon]) => [lon, lat] as [number, number],
      )
      if (coordinates.length < 2) continue
      const mode: RouteLineMode =
        seg.mode === 'car' || seg.mode === 'transit' ? seg.mode : 'walk'
      lines.push({ mode, coordinates })
    } catch {
      // ignore malformed provider geometry
    }
  }
  if (lines.length > 0) return lines

  const fallback = tripRouteLineCoordinates({
    polyline: opts.routePolyline,
    routeVerified: opts.routeVerified,
  })
  if (fallback.length >= 2) {
    return [{ mode: 'walk', coordinates: fallback }]
  }
  return []
}
