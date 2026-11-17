import { describe, expect, it } from 'vitest'
import { tripRouteLineCoordinates, tripVerifiedSegmentLines } from './tripRouteLine'

const SAMPLE = '_p~iF~ps|U_ulLnnqC_mqNvxq`@'

describe('tripRouteLineCoordinates', () => {
  it('returns empty when route is unverified even if polyline present', () => {
    expect(
      tripRouteLineCoordinates({
        polyline: SAMPLE,
        routeVerified: false,
      }),
    ).toEqual([])
  })

  it('returns empty when polyline is missing (no straight-line fallback)', () => {
    expect(tripRouteLineCoordinates({ polyline: null, routeVerified: true })).toEqual([])
    expect(tripRouteLineCoordinates({ polyline: '', routeVerified: true })).toEqual([])
    expect(tripRouteLineCoordinates({ routeVerified: true })).toEqual([])
  })

  it('decodes verified provider polyline', () => {
    const coords = tripRouteLineCoordinates({
      polyline: SAMPLE,
      routeVerified: true,
    })
    expect(coords.length).toBeGreaterThanOrEqual(2)
    expect(coords[0]).toHaveLength(2)
  })
})

describe('tripVerifiedSegmentLines', () => {
  it('draws each verified segment polyline by mode when day overview is null', () => {
    const lines = tripVerifiedSegmentLines({
      routePolyline: null,
      routeVerified: true,
      segments: [
        { mode: 'walk', verified: true, polyline: SAMPLE },
        { mode: 'car', verified: true, polyline: SAMPLE },
        { mode: 'walk', verified: false, polyline: SAMPLE },
        { mode: 'car', verified: true, polyline: null },
      ],
    })
    expect(lines).toHaveLength(2)
    expect(lines[0].mode).toBe('walk')
    expect(lines[1].mode).toBe('car')
    expect(lines[0].coordinates.length).toBeGreaterThanOrEqual(2)
  })

  it('falls back to day overview polyline only when no segment geometry', () => {
    const lines = tripVerifiedSegmentLines({
      routePolyline: SAMPLE,
      routeVerified: true,
      segments: [{ mode: 'walk', verified: true, polyline: null }],
    })
    expect(lines).toHaveLength(1)
    expect(lines[0].coordinates.length).toBeGreaterThanOrEqual(2)
  })

  it('never invents geometry from empty segments', () => {
    expect(
      tripVerifiedSegmentLines({
        routePolyline: null,
        routeVerified: true,
        segments: [{ mode: 'walk', verified: true }],
      }),
    ).toEqual([])
  })
})
