import type { HotelMatchLevel } from '../types/vision'
import { hotels } from '../data/hotels'
import {
  colorDistance,
  computeAHash,
  computeColorProfile,
  hammingDistance,
  inferVisualTagsFromProfile,
  type ColorProfile,
} from './imageFingerprint'

export type CatalogImageEntry = {
  hotelId: string
  imageUrl: string
  tags: string[]
  hash?: bigint
  color?: ColorProfile
}

export type ImageMatch = {
  hotelId: string
  imageUrl: string
  tags: string[]
  hashDistance: number
  colorDistance: number
  score: number
}

export type SearchDiagnostics = {
  mode: string
  queryType: 'full-image' | 'region-crop'
  fingerprintMatch: boolean
  bestHashDistance: number | null
  topImageMatches: Array<{ hotelId: string; imageUrl: string; score: number; hashDistance: number }>
  hotelAggregation: Array<{ hotelId: string; score: number; matchLevel: HotelMatchLevel }>
  provider: 'ahash+color'
}

let catalogReady: Promise<CatalogImageEntry[]> | null = null
let lastDiagnostics: SearchDiagnostics | null = null

export function getLastSearchDiagnostics() {
  return lastDiagnostics
}

function buildCatalogEntries(): CatalogImageEntry[] {
  const entries: CatalogImageEntry[] = []
  for (const hotel of hotels) {
    hotel.images.forEach((imageUrl, index) => {
      const tags = hotel.visualTags?.length
        ? hotel.visualTags
        : hotel.matchedFeatures.map((f) => f.toLowerCase())
      const roleTags =
        index === 0
          ? ['фасад', 'hero']
          : index === 1
            ? ['бассейн', 'вода']
            : index === 2
              ? ['территория', 'вид']
              : ['атмосфера']
      entries.push({
        hotelId: hotel.id,
        imageUrl,
        tags: Array.from(new Set([...tags.map((t) => t.toLowerCase()), ...roleTags])),
      })
    })
  }
  return entries
}

async function ensureCatalog(): Promise<CatalogImageEntry[]> {
  if (!catalogReady) {
    catalogReady = (async () => {
      const entries = buildCatalogEntries()
      await Promise.all(
        entries.map(async (entry) => {
          try {
            entry.hash = await computeAHash(entry.imageUrl)
            entry.color = await computeColorProfile(entry.imageUrl)
          } catch {
            // leave unset; match will skip
          }
        }),
      )
      return entries
    })()
  }
  return catalogReady
}

const EXACT_HASH_MAX = 12
const NEAR_HASH_MAX = 22

function tagOverlap(queryTags: string[], entryTags: string[]): number {
  const q = new Set(queryTags.map((t) => t.toLowerCase()))
  let hit = 0
  for (const t of entryTags) if (q.has(t.toLowerCase())) hit += 1
  return hit
}

export async function retrieveCatalogMatches(options: {
  querySource: File | Blob | string
  mode: 'full-image' | 'freehand-region' | 'selected-region'
  regionBoostTags?: string[]
}): Promise<{
  matches: Array<{
    hotelId: string
    matchLevel: HotelMatchLevel
    matchedFeatures: string[]
    isExactCandidate: boolean
    matchedImageUrl: string
    score: number
  }>
  exactFound: boolean
  diagnostics: SearchDiagnostics
}> {
  const catalog = await ensureCatalog()
  const queryHash = await computeAHash(options.querySource)
  const queryColor = await computeColorProfile(options.querySource)
  const inferredTags = inferVisualTagsFromProfile(queryColor)
  const boostTags = options.regionBoostTags?.length ? options.regionBoostTags : inferredTags
  const isRegion = options.mode !== 'full-image'

  const imageMatches: ImageMatch[] = []
  for (const entry of catalog) {
    if (entry.hash === undefined || !entry.color) continue
    const hashDist = hammingDistance(queryHash, entry.hash)
    const cDist = colorDistance(queryColor, entry.color)
    const tagBoost = isRegion ? tagOverlap(boostTags, entry.tags) * 0.14 : tagOverlap(boostTags, entry.tags) * 0.06
    // Lower is better for distances; convert to score 0..1
    const hashScore = Math.max(0, 1 - hashDist / 36)
    const colorScore = Math.max(0, 1 - cDist / 3)
    const score = hashScore * 0.58 + colorScore * 0.42 + tagBoost
    imageMatches.push({
      hotelId: entry.hotelId,
      imageUrl: entry.imageUrl,
      tags: entry.tags,
      hashDistance: hashDist,
      colorDistance: cDist,
      score,
    })
  }

  imageMatches.sort((a, b) => b.score - a.score)

  const byHotel = new Map<
    string,
    { scores: number[]; best: ImageMatch; hashDistances: number[] }
  >()
  for (const match of imageMatches) {
    const existing = byHotel.get(match.hotelId)
    if (!existing) {
      byHotel.set(match.hotelId, {
        scores: [match.score],
        best: match,
        hashDistances: [match.hashDistance],
      })
      continue
    }
    existing.scores.push(match.score)
    existing.hashDistances.push(match.hashDistance)
    if (match.score > existing.best.score) existing.best = match
  }

  const hotelRows = Array.from(byHotel.entries())
    .map(([hotelId, data]) => {
      const top = data.scores.sort((a, b) => b - a).slice(0, 3)
      const avg = top.reduce((s, v) => s + v, 0) / top.length
      const hotelScore = data.best.score * 0.7 + avg * 0.3
      const bestHash = Math.min(...data.hashDistances)
      return { hotelId, hotelScore, best: data.best, bestHash }
    })
    .sort((a, b) => b.hotelScore - a.hotelScore)

  const bestOverall = hotelRows[0]
  const exactFound = Boolean(bestOverall && bestOverall.bestHash <= EXACT_HASH_MAX)

  const matches = hotelRows.slice(0, 4).map((row, index) => {
    let matchLevel: HotelMatchLevel = 'possible'
    let isExactCandidate = false
    if (row.bestHash <= EXACT_HASH_MAX && index === 0) {
      matchLevel = 'very-high'
      isExactCandidate = true
    } else if (row.bestHash <= NEAR_HASH_MAX || row.hotelScore >= 0.62) {
      matchLevel = 'high'
    } else if (row.hotelScore >= 0.42) {
      matchLevel = 'possible'
    }

    const features = Array.from(
      new Set([...(isRegion ? boostTags : inferredTags), ...row.best.tags]),
    ).slice(0, 4)

    return {
      hotelId: row.hotelId,
      matchLevel,
      matchedFeatures: features,
      isExactCandidate,
      matchedImageUrl: row.best.imageUrl,
      score: row.hotelScore,
    }
  })

  // Honest fallback: if no strong signal, demote exact claim and keep atmosphere list
  const strong = matches.some((m) => m.matchLevel === 'very-high' || m.matchLevel === 'high')
  if (!strong) {
    for (const m of matches) {
      m.isExactCandidate = false
      m.matchLevel = 'possible'
    }
  }

  const diagnostics: SearchDiagnostics = {
    mode: options.mode,
    queryType: isRegion ? 'region-crop' : 'full-image',
    fingerprintMatch: exactFound,
    bestHashDistance: bestOverall?.bestHash ?? null,
    topImageMatches: imageMatches.slice(0, 5).map((m) => ({
      hotelId: m.hotelId,
      imageUrl: m.imageUrl,
      score: Number(m.score.toFixed(3)),
      hashDistance: m.hashDistance,
    })),
    hotelAggregation: matches.map((m) => ({
      hotelId: m.hotelId,
      score: Number(m.score.toFixed(3)),
      matchLevel: m.matchLevel,
    })),
    provider: 'ahash+color',
  }
  lastDiagnostics = diagnostics

  return { matches, exactFound, diagnostics }
}

/** Test helper: compare two sources via aHash. */
export async function hashDistanceBetween(
  a: File | Blob | string,
  b: File | Blob | string,
): Promise<number> {
  const ha = await computeAHash(a)
  const hb = await computeAHash(b)
  return hammingDistance(ha, hb)
}
