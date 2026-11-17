import { getHotelById, similarCheaper } from '../data/hotels'
import type { HotelMatch, MatchScenario, VisualAnalysis } from '../types/vision'
import type { VisualSearchInput } from '../types/visualSearch'
import { isRegionSearchMode } from '../types/visualSearch'
import { retrieveCatalogMatches, getLastSearchDiagnostics } from '../vision/catalogRetrieval'
import { computeColorProfile, inferVisualTagsFromProfile } from '../vision/imageFingerprint'

let activeScenario: MatchScenario = 'exact'

const CLOUD_API_URL = (import.meta.env.VITE_VISUAL_SEARCH_API_URL as string | undefined)?.replace(/\/$/, '')

export function setMatchScenario(scenario: MatchScenario) {
  activeScenario = scenario
}

export function getMatchScenario(): MatchScenario {
  return activeScenario
}

export { getLastSearchDiagnostics }

async function resolveQuerySource(input: VisualSearchInput): Promise<File | Blob | string> {
  if (isRegionSearchMode(input.mode)) {
    if (input.boxedCropBlob) return input.boxedCropBlob
    if (input.maskedCropBlob) return input.maskedCropBlob
  }
  return input.originalFile
}

type GigaAssistPayload = {
  assist?: {
    features?: string[]
    refined_query?: string | null
    vision_invoked?: boolean
    model?: string | null
    limitation?: string | null
  } | null
  vision_invoked?: boolean
  model?: string | null
  limitation?: string | null
}

/** Optional GigaChat Vision — multipart image only; does not replace identity. */
async function fetchGigaChatVisionAssist(
  input: VisualSearchInput,
): Promise<VisualAnalysis['gigachatAssist'] | undefined> {
  if (!CLOUD_API_URL) return undefined
  try {
    const query = await resolveQuerySource(input)
    const blob =
      typeof query === 'string' ? await fetch(query).then((r) => r.blob()) : query
    const form = new FormData()
    form.append('file', blob, isRegionSearchMode(input.mode) ? 'crop.jpg' : 'query.jpg')
    form.append('mode', input.mode)
    if (isRegionSearchMode(input.mode)) {
      form.append('crop_hint', 'выделенный фрагмент')
    }
    const res = await fetch(`${CLOUD_API_URL}/api/visual-search/gigachat-assist`, {
      method: 'POST',
      body: form,
      signal: AbortSignal.timeout(45000),
    })
    if (!res.ok) return undefined
    const data = (await res.json()) as GigaAssistPayload
    const assist = data.assist
    const visionInvoked = Boolean(data.vision_invoked ?? assist?.vision_invoked)
    const features = Array.isArray(assist?.features) ? assist!.features!.filter(Boolean) : []
    return {
      features,
      refinedQuery: assist?.refined_query ?? null,
      visionInvoked,
      model: data.model ?? assist?.model ?? null,
      limitation: data.limitation ?? assist?.limitation ?? null,
    }
  } catch {
    return undefined
  }
}

export async function analyzeVisualSearchInput(
  input: VisualSearchInput,
): Promise<VisualAnalysis> {
  await delay(280)
  const query = await resolveQuerySource(input)
  const profile = await computeColorProfile(query)
  const tags = inferVisualTagsFromProfile(profile)
  const hints = input.featureHints?.length
    ? input.featureHints.map((h) => h.toLowerCase())
    : tags

  // Local fingerprint first; GigaChat Vision is assistive enrichment only.
  const giga = await fetchGigaChatVisionAssist(input)
  const mergedFeatures = [
    ...hints,
    ...(giga?.features ?? []).map((f) => f.toLowerCase()),
  ]
  const unique = [...new Set(mergedFeatures)].slice(0, 12)

  if (isRegionSearchMode(input.mode)) {
    return {
      visualTags: unique,
      inferredEnvironment: ['курорт', 'открытая территория'],
      possibleText: [],
      detectedFeatures: unique,
      gigachatAssist: giga,
    }
  }

  return {
    visualTags: unique,
    inferredEnvironment: ['курорт', 'средиземноморье'],
    possibleText: [],
    detectedFeatures: unique,
    gigachatAssist: giga,
  }
}

/** @deprecated use analyzeVisualSearchInput */
export async function analyzeImage(file: File): Promise<VisualAnalysis> {
  return analyzeVisualSearchInput({
    originalFile: file,
    originalPreviewUrl: '',
    mode: 'full-image',
  })
}

type CloudHotelHit = {
  hotel_id: string
  hotel_name?: string | null
  chain?: string | null
  latitude?: number | null
  longitude?: number | null
  score: number
  matchedImage?: {
    image_id?: string
    image_url?: string
    source_reference?: string
    score?: number
  }
}

/** Budget / roadside chains that look wrong in a leisure travel product. */
const LOW_QUALITY_CHAIN_RE =
  /motel\s*6|americinn|super\s*8|days?\s*inn|red\s*roof|econo\s*lodge|travelodge|knights?\s*inn|howard\s*johnson|quality\s*inn|comfort\s*inn|la\s*quinta|microtel|studio\s*6|extended\s*stay|candlewood|wingate|ramada|baymont|country\s*inn|towneplace|residence\s*inn|fairfield\s*inn|home2\s*suites|homewood|hampton\s*inn|holiday\s*inn\s*express|rodeo\s*inn|budget\s*inn|palace\s*inn/i

/** Crowd-sourced TraffickCam dumps — often messy rooms, upside-down, bathrooms. */
const LOW_QUALITY_IMAGE_RE = /image-submissions\.s3|traffickcam/i

function isPresentableCloudHit(h: CloudHotelHit): boolean {
  const label = `${h.hotel_name ?? ''} ${h.chain ?? ''}`
  if (LOW_QUALITY_CHAIN_RE.test(label)) return false
  const url = h.matchedImage?.image_url ?? ''
  if (url && LOW_QUALITY_IMAGE_RE.test(url)) return false
  const ref = h.matchedImage?.source_reference ?? ''
  if (/traffickcam/i.test(ref)) return false
  // Live Hotels-50K identity scores are often ~0.3–0.5 — too weak to show as “found”.
  if ((h.score ?? 0) < 0.72) return false
  return true
}

async function findCloudHotelMatches(
  input: VisualSearchInput,
  features: string[],
): Promise<HotelMatch[] | null> {
  if (!CLOUD_API_URL) return null
  try {
    const query = await resolveQuerySource(input)
    const blob =
      typeof query === 'string'
        ? await fetch(query).then((r) => r.blob())
        : query
    const form = new FormData()
    form.append('file', blob, 'query.jpg')
    // Cloud is best-effort: fail fast to local catalog fallback when Qdrant is slow.
    const res = await fetch(`${CLOUD_API_URL}/api/visual-search?mode=${encodeURIComponent(input.mode)}`, {
      method: 'POST',
      body: form,
      signal: AbortSignal.timeout(25000),
    })
    if (!res.ok) return null
    const data = (await res.json()) as {
      backend?: string
      hotels?: CloudHotelHit[]
    }
    if (data.backend === 'mock' || data.backend === 'mock_fallback') {
      return null
    }
    if (!data.hotels?.length) return null

    const presentable = data.hotels.filter(isPresentableCloudHit)
    // Prefer curated demo resorts over weak / ugly Hotels-50K cards.
    if (!presentable.length) return null

    return presentable.map((h, index) => {
      const score = h.score ?? 0
      let matchLevel: HotelMatch['matchLevel'] = 'possible'
      if (score >= 0.88) matchLevel = 'very-high'
      else if (score >= 0.78) matchLevel = 'high'
      const local = getHotelById(h.hotel_id)
      const imageUrl = h.matchedImage?.image_url
      const safeImage =
        imageUrl && !LOW_QUALITY_IMAGE_RE.test(imageUrl) ? imageUrl : local?.images[0]
      return {
        hotelId: local?.id ?? h.hotel_id,
        matchLevel,
        matchedFeatures: [
          ...(features.slice(0, 2)),
          ...(h.chain && !LOW_QUALITY_CHAIN_RE.test(h.chain) ? [h.chain] : []),
        ].slice(0, 4),
        isExactCandidate: index === 0 && matchLevel === 'very-high',
        matchedImageUrl: safeImage,
        score,
        hotelName: h.hotel_name ?? local?.name,
        chain: h.chain ?? undefined,
        latitude: h.latitude ?? undefined,
        longitude: h.longitude ?? undefined,
        source: 'cloud' as const,
      }
    })
  } catch {
    return null
  }
}

export async function findHotelMatches(
  analysis: VisualAnalysis,
  input?: VisualSearchInput,
): Promise<HotelMatch[]> {
  await delay(320)

  if (!input) {
    return atmosphereFallback(analysis.detectedFeatures)
  }

  if (activeScenario === 'none') {
    return atmosphereFallback(analysis.detectedFeatures)
  }
  if (activeScenario === 'multiple') {
    return ['rixos-premium-tekirova', 'akka-antedon', 'nirvana-mediterranean', 'seven-seas-life'].map(
      (hotelId, index) => ({
        hotelId,
        matchLevel: index === 0 ? ('high' as const) : ('possible' as const),
        matchedFeatures: analysis.detectedFeatures.slice(0, 3),
        isExactCandidate: false,
        matchedImageUrl: getHotelById(hotelId)?.images[0],
        source: 'mock' as const,
      }),
    )
  }

  const cloud = await findCloudHotelMatches(input, analysis.detectedFeatures)
  if (cloud?.length) {
    if (activeScenario === 'region' || isRegionSearchMode(input.mode)) {
      return cloud.map((m) => ({
        ...m,
        isExactCandidate: false,
        matchLevel: m.matchLevel === 'very-high' ? 'high' : m.matchLevel,
      }))
    }
    return cloud
  }

  const query = await resolveQuerySource(input)
  const { matches, exactFound } = await retrieveCatalogMatches({
    querySource: query,
    mode: input.mode,
    regionBoostTags: analysis.detectedFeatures,
  })

  const localMatches = matches.map((m) => ({ ...m, source: 'local' as const }))

  if (activeScenario === 'region' || isRegionSearchMode(input.mode)) {
    if (!localMatches.length) return atmosphereFallback(analysis.detectedFeatures)
    return localMatches.map((m) => ({
      ...m,
      isExactCandidate: false,
      matchLevel: m.matchLevel === 'very-high' ? 'high' : m.matchLevel,
      // Prefer polished demo covers over any leftover dump URL.
      matchedImageUrl: getHotelById(m.hotelId)?.images[0] ?? m.matchedImageUrl,
    }))
  }

  if (!exactFound && !localMatches.some((m) => m.matchLevel === 'very-high' || m.matchLevel === 'high')) {
    return atmosphereFallback(analysis.detectedFeatures)
  }

  return localMatches.map((m) => ({
    ...m,
    matchedImageUrl: getHotelById(m.hotelId)?.images[0] ?? m.matchedImageUrl,
  }))
}

function atmosphereFallback(features: string[]): HotelMatch[] {
  return similarCheaper.map((item) => ({
    hotelId: item.hotelId,
    matchLevel: 'possible' as const,
    matchedFeatures: item.features.length ? item.features : features.slice(0, 2),
    isExactCandidate: false,
    matchedImageUrl: item.image,
    source: 'mock' as const,
  }))
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
