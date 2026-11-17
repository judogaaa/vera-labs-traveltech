import { describe, expect, it } from 'vitest'
import { catalogCoverUrl, whySelectedSummary } from '../labels'
import type { CatalogHotel } from '../../../types/catalog'

describe('ResultCard helpers', () => {
  it('uses only catalog image URLs and never invents a cover', () => {
    expect(catalogCoverUrl(null)).toBeNull()
    expect(catalogCoverUrl(undefined)).toBeNull()
    expect(
      catalogCoverUrl({
        id: 'h1',
        name: 'Test',
        chain: null,
        latitude: null,
        longitude: null,
        images: [],
        provider: 'curated',
        image_count: 0,
        source: 'curated',
      } satisfies CatalogHotel),
    ).toBeNull()

    const withPhoto = {
      id: 'h1',
      name: 'Test',
      chain: null,
      latitude: null,
      longitude: null,
      images: ['https://cdn.example/hotel.jpg'],
      provider: 'curated',
      image_count: 1,
      source: 'curated',
    } satisfies CatalogHotel
    expect(catalogCoverUrl(withPhoto)).toBe('https://cdn.example/hotel.jpg')
  })

  it('summarizes why-selected from API buckets only', () => {
    const text = whySelectedSummary({
      matched: [{ attribute_key: 'walk_to_metro' }],
      unmatched: [{ attribute_key: 'external_noise_risk' }],
      unknown: [{ attribute_key: 'blackout_curtains' }],
    })
    expect(text).toContain('совпало')
    expect(text).toContain('Пешком до метро')
    expect(text).toContain('неизвестно')
    expect(text).toContain('Плотные шторы')
  })
})
