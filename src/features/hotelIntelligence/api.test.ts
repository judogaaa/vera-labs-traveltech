import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  hotelDisplayName,
  hotelLatLon,
  parseHotelIntelligenceError,
  searchHotels,
} from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('hotel intelligence api client', () => {
  it('parses FastAPI detail objects and strings', () => {
    expect(
      parseHotelIntelligenceError(
        { detail: { code: 'hotel_not_found', message: 'missing' } },
        'fallback',
      ),
    ).toEqual({ code: 'hotel_not_found', message: 'missing' })

    expect(parseHotelIntelligenceError({ detail: 'boom' }, 'fallback')).toEqual({
      code: 'error',
      message: 'boom',
    })

    expect(parseHotelIntelligenceError(null, 'fallback')).toEqual({
      code: 'error',
      message: 'fallback',
    })
  })

  it('normalizes search payload and never invents results', async () => {
    const payload = {
      query: 'тихий отель',
      requested: [{ key: 'external_noise_risk', role: 'must', constraint: {} }],
      results: [
        {
          hotel_id: 'ist-demo-001',
          name: 'Demo',
          score: 1.2,
          matched: [{ attribute_key: 'external_noise_risk', status: 'estimated' }],
          unmatched: [],
          unknown: [],
          conflicts: [],
        },
      ],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    const data = await searchHotels('тихий отель', 10)
    expect(data.results).toHaveLength(1)
    expect(data.results[0].hotel_id).toBe('ist-demo-001')
    expect(data.requested[0].key).toBe('external_noise_risk')
  })

  it('surfaces network_unavailable without fabricating hotels', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(searchHotels('тихий')).rejects.toMatchObject({
      code: 'network_unavailable',
    })
  })

  it('reads lat/lon aliases and display name safely', () => {
    expect(hotelLatLon({ hotel_id: 'a', latitude: 41, longitude: 29 })).toEqual({
      lat: 41,
      lon: 29,
    })
    expect(hotelLatLon({ hotel_id: 'a' })).toBeNull()
    expect(hotelDisplayName({ hotel_id: 'x', name: 'Hyatt' })).toBe('Hyatt')
    expect(hotelDisplayName({ hotel_id: 'x' })).toBe('x')
  })
})
