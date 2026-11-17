import type { CatalogHotel } from '../types/catalog'
import type { Hotel } from '../types/hotel'
import { hotels as demoHotels } from './hotels'

/** Served from /public — never import as a JS module (1.6MB wedges Vite transform). */
const CURATED_SLIM_URL = '/data/curatedHotelsSlim.json'

type Hotels50kRow = {
  id: string
  name: string
  chain: string | null
  latitude: number | null
  longitude: number | null
  images: string[]
  provider?: string
  image_count: number
}

type RegionHotelRow = Hotels50kRow & {
  source_hotel_id?: string
  city: string
  country: string
}

type CuratedSlimRow = {
  id: string
  name: string
  chain: string | null
  latitude: number | null
  longitude: number | null
  images: string[]
  provider?: string
  image_count: number
  city?: string
  country?: string
  country_code?: string
  resort_area?: string
  description?: string
  amenities?: string[]
  pricePerNight?: number | null
  price_status?: string
  curation_score?: number
}

/** Optional generated dumps — loaded on demand, never eager-transformed into the home graph. */
const optionalCatalogLoaders = import.meta.glob<{ default: Hotels50kRow[] | RegionHotelRow[] }>(
  './*Catalog.json',
)

const BATHROOM_URL_RE =
  /bathroom|toilet|restroom|washroom|lavatory|shower|bathtub|\bbath\b|\/bath[_/-]|_bath[_/-]|sink|wc[_/-]/i

function coverScore(url: string): number {
  let score = 0
  if (BATHROOM_URL_RE.test(url)) score -= 100
  if (/i\.travelapi\.com|expedia|hotels\.com/i.test(url)) score += 40
  if (/image-submissions\.s3/i.test(url)) score -= 25
  if (/exterior|facade|pool|lobby|beach|resort|aerial|night/i.test(url)) score += 15
  return score
}

function orderImagesForCatalog(images: string[]): string[] {
  if (images.length <= 1) return images
  return [...images].sort((a, b) => coverScore(b) - coverScore(a))
}

function normalizeChain(chain: string | null | undefined): string | null {
  if (!chain) return null
  const trimmed = chain.trim()
  if (!trimmed || trimmed.toLowerCase() === 'unknown') return null
  return trimmed
}

function isCatalogQuality(row: {
  city?: string
  country?: string
  images?: string[]
  name?: string
  provider?: string
  source?: string
}): boolean {
  if (!row.city?.trim() || !row.country?.trim()) return false
  if (!row.name?.trim()) return false
  const images = row.images ?? []
  const minImages = row.provider === 'curated' || row.source === 'curated' ? 1 : 2
  if (images.length < minImages) return false
  if (images.every((u) => BATHROOM_URL_RE.test(u))) return false
  return true
}

function ensureCardCopy(hotel: CatalogHotel): CatalogHotel {
  const city = hotel.city?.trim() || ''
  const country = hotel.country?.trim() || ''
  let description = hotel.description?.trim() || ''
  if (!description && city && country) {
    const tone = /resort|beach|palace|rixos|marina/i.test(hotel.name)
      ? 'Пляжный курортный отель'
      : 'Отель'
    description =
      `${tone} «${hotel.name}» в ${city}, ${country}. ` +
      `Подходит для leisure-поездки: в карточке — ориентир по локации и типу размещения. ` +
      `Описание составлено для каталога О!Хочу, без копирования чужих отзывов.`
    if (description.length < 250) {
      description += ` Направление ${country} — популярный маршрут у российских туристов.`
    }
    description = description.slice(0, 500)
  }
  let pricePerNight = hotel.pricePerNight
  let price_status = hotel.price_status
  if (pricePerNight == null || pricePerNight <= 0) {
    pricePerNight = undefined
    price_status = price_status || 'unavailable'
  } else if (price_status === 'ui_estimate') {
    price_status = 'ui_estimate'
  }
  return { ...hotel, description, pricePerNight, price_status }
}

function mapCurated(rows: CuratedSlimRow[]): CatalogHotel[] {
  return rows
    .filter((row) => isCatalogQuality(row))
    .map((row) =>
      ensureCardCopy({
        id: row.id,
        name: row.name,
        chain: normalizeChain(row.chain),
        latitude: row.latitude,
        longitude: row.longitude,
        images: orderImagesForCatalog(row.images ?? []),
        provider: row.provider ?? 'curated',
        image_count: row.image_count ?? row.images?.length ?? 0,
        city: row.city,
        country: row.country,
        country_code: row.country_code,
        resort_area: row.resort_area,
        description: row.description,
        amenities: row.amenities,
        pricePerNight: row.pricePerNight ?? undefined,
        price_status: row.price_status,
        source: 'curated' as const,
      }),
    )
}

function mapRegion(rows: RegionHotelRow[]): CatalogHotel[] {
  return rows.filter(isCatalogQuality).map((row) => {
    const images = orderImagesForCatalog(row.images ?? [])
    return ensureCardCopy({
      id: row.id,
      name: row.name,
      chain: normalizeChain(row.chain),
      latitude: row.latitude,
      longitude: row.longitude,
      images,
      provider: row.provider ?? 'hotels50k',
      image_count: row.image_count ?? images.length,
      city: row.city,
      country: row.country,
      source: 'hotels50k' as const,
    })
  })
}

function mapHotels50k(
  rows: Hotels50kRow[],
  regionSourceIds: Set<string>,
  regionCatalogIds: Set<string>,
): CatalogHotel[] {
  return rows
    .filter((row) => !regionSourceIds.has(row.id) && !regionCatalogIds.has(row.id))
    .map((row) => ({
      id: row.id,
      name: row.name,
      chain: normalizeChain(row.chain),
      latitude: row.latitude,
      longitude: row.longitude,
      images: orderImagesForCatalog(row.images ?? []),
      provider: row.provider ?? 'hotels50k',
      image_count: row.image_count ?? row.images?.length ?? 0,
      source: 'hotels50k' as const,
    }))
}

const demoCatalog: CatalogHotel[] = demoHotels.map((hotel) =>
  ensureCardCopy({
    id: hotel.id,
    name: hotel.name,
    chain: null,
    latitude: null,
    longitude: null,
    images: hotel.images,
    provider: 'demo',
    image_count: hotel.images.length,
    city: hotel.city,
    country: hotel.country,
    rating: hotel.rating,
    reviewCount: hotel.reviewCount,
    pricePerNight: hotel.pricePerNight,
    amenities: hotel.amenities,
    description: hotel.description,
    source: 'demo' as const,
  }),
)

/** Starts with demo only; expands after `ensureCatalogReady()`. */
export let catalogHotels: CatalogHotel[] = [...demoCatalog]

const byId = new Map<string, CatalogHotel>()
for (const h of catalogHotels) byId.set(h.id, h)

function rebuildIndexes(
  curated: CatalogHotel[],
  region: CatalogHotel[],
  hotels50kLookup: CatalogHotel[],
) {
  catalogHotels = curated.length > 0 ? [...curated, ...demoCatalog] : [...region, ...demoCatalog]
  byId.clear()
  for (const h of [...catalogHotels, ...region, ...hotels50kLookup]) {
    if (!byId.has(h.id)) byId.set(h.id, h)
  }
}

let loadPromise: Promise<void> | null = null

/** Fetch curated (+ optional) catalogs once. Safe to call from any screen. */
export function ensureCatalogReady(): Promise<void> {
  if (!loadPromise) {
    loadPromise = (async () => {
      let curated: CatalogHotel[] = []
      try {
        const res = await fetch(CURATED_SLIM_URL)
        if (res.ok) {
          const raw = (await res.json()) as CuratedSlimRow[]
          curated = mapCurated(Array.isArray(raw) ? raw : [])
        }
      } catch {
        curated = []
      }

      let regionHotelsRaw: RegionHotelRow[] = []
      let hotels50kRaw: Hotels50kRow[] = []
      const regionLoader = optionalCatalogLoaders['./regionHotelsCatalog.json']
      const h50kLoader = optionalCatalogLoaders['./hotels50kCatalog.json']
      if (regionLoader) {
        try {
          const mod = await regionLoader()
          regionHotelsRaw = (mod.default ?? []) as RegionHotelRow[]
        } catch {
          regionHotelsRaw = []
        }
      }
      if (h50kLoader) {
        try {
          const mod = await h50kLoader()
          hotels50kRaw = (mod.default ?? []) as Hotels50kRow[]
        } catch {
          hotels50kRaw = []
        }
      }

      const regionCatalog = mapRegion(regionHotelsRaw)
      const regionSourceIds = new Set(
        regionHotelsRaw.map((r) => r.source_hotel_id).filter((id): id is string => Boolean(id)),
      )
      const regionCatalogIds = new Set(regionCatalog.map((r) => r.id))
      const hotels50kLookup = mapHotels50k(hotels50kRaw, regionSourceIds, regionCatalogIds)
      rebuildIndexes(curated, regionCatalog, hotels50kLookup)
    })()
  }
  return loadPromise
}

export function getCatalogHotelById(id: string): CatalogHotel | undefined {
  return byId.get(id)
}

export function catalogToHotel(entry: CatalogHotel): Hotel {
  const demo = demoHotels.find((h) => h.id === entry.id)
  if (demo) return demo

  if (entry.city && entry.country) {
    return {
      id: entry.id,
      name: entry.name,
      city: entry.city,
      country: entry.country,
      address: [entry.city, entry.country].filter(Boolean).join(', '),
      rating: entry.rating ?? 0,
      reviewCount: entry.reviewCount ?? 0,
      pricePerNight: entry.pricePerNight ?? 0,
      images: entry.images,
      amenities: entry.amenities ?? (entry.chain ? [entry.chain] : []),
      description:
        entry.description ??
        `Отель в направлении ${entry.city}, ${entry.country}. В каталоге ${entry.image_count} фото.`,
      matchedFeatures: entry.amenities?.slice(0, 4) ?? (entry.chain ? [entry.chain] : []),
      visualTags: entry.chain ? [entry.chain.toLowerCase()] : [],
      rooms: [],
    }
  }

  const place =
    entry.chain ||
    (entry.latitude != null && entry.longitude != null
      ? `${entry.latitude.toFixed(2)}, ${entry.longitude.toFixed(2)}`
      : 'Hotels-50K')

  return {
    id: entry.id,
    name: entry.name,
    city: place,
    country: entry.provider === 'hotels50k' ? 'Hotels-50K' : '',
    address: '',
    rating: entry.rating ?? 0,
    reviewCount: entry.reviewCount ?? 0,
    pricePerNight: entry.pricePerNight ?? 0,
    images: entry.images,
    amenities: entry.amenities ?? (entry.chain ? [entry.chain] : []),
    description:
      entry.description ??
      `Отель из индекса Hotels-50K. В карточке ${entry.image_count} фото.`,
    matchedFeatures: entry.chain ? [entry.chain] : [],
    visualTags: entry.chain ? [entry.chain.toLowerCase()] : [],
    rooms: [],
  }
}

export function getTopChains(limit = 24): string[] {
  const counts = new Map<string, number>()
  for (const h of catalogHotels) {
    if (!h.chain) continue
    counts.set(h.chain, (counts.get(h.chain) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([name]) => name)
}

export function getCatalogCountries(): string[] {
  const preferred = ['Турция', 'Египет', 'ОАЭ', 'Таиланд', 'Вьетнам', 'Греция', 'Тунис']
  const found = new Set<string>()
  for (const h of catalogHotels) {
    if (h.country) found.add(h.country)
  }
  const ordered = preferred.filter((c) => found.has(c))
  const rest = [...found].filter((c) => !preferred.includes(c)).sort((a, b) => a.localeCompare(b, 'ru'))
  return [...ordered, ...rest]
}
