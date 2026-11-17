import { loadImageElement } from '../utils/loadImage'

const HASH_SIZE = 8

/** Average hash (aHash) as 64-bit BigInt string for stable compare. */
export async function computeAHash(source: File | Blob | string): Promise<bigint> {
  const image = await loadImageElement(source)
  const canvas = document.createElement('canvas')
  canvas.width = HASH_SIZE
  canvas.height = HASH_SIZE
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) throw new Error('Canvas unavailable')
  ctx.drawImage(image, 0, 0, HASH_SIZE, HASH_SIZE)
  const { data } = ctx.getImageData(0, 0, HASH_SIZE, HASH_SIZE)

  const grays: number[] = []
  for (let i = 0; i < data.length; i += 4) {
    grays.push(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2])
  }
  const avg = grays.reduce((a, b) => a + b, 0) / grays.length

  let hash = 0n
  for (let i = 0; i < grays.length; i++) {
    if (grays[i] >= avg) hash |= 1n << BigInt(i)
  }
  return hash
}

export function hammingDistance(a: bigint, b: bigint): number {
  let x = a ^ b
  let count = 0
  while (x > 0n) {
    count += Number(x & 1n)
    x >>= 1n
  }
  return count
}

export type ColorProfile = {
  meanR: number
  meanG: number
  meanB: number
  blueShare: number
  greenShare: number
  warmShare: number
  brightShare: number
}

export async function computeColorProfile(source: File | Blob | string): Promise<ColorProfile> {
  const image = await loadImageElement(source)
  const size = 32
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) throw new Error('Canvas unavailable')
  ctx.drawImage(image, 0, 0, size, size)
  const { data } = ctx.getImageData(0, 0, size, size)

  let r = 0
  let g = 0
  let b = 0
  let blue = 0
  let green = 0
  let warm = 0
  let bright = 0
  const n = data.length / 4

  for (let i = 0; i < data.length; i += 4) {
    const pr = data[i]
    const pg = data[i + 1]
    const pb = data[i + 2]
    const a = data[i + 3]
    if (a < 40) continue
    r += pr
    g += pg
    b += pb
    const lum = (pr + pg + pb) / 3
    if (lum > 180) bright += 1
    if (pb > pr + 15 && pb > pg + 5) blue += 1
    else if (pg > pr + 10 && pg > pb + 5) green += 1
    else if (pr > pg && pr > pb) warm += 1
  }

  return {
    meanR: r / n,
    meanG: g / n,
    meanB: b / n,
    blueShare: blue / n,
    greenShare: green / n,
    warmShare: warm / n,
    brightShare: bright / n,
  }
}

export function inferVisualTagsFromProfile(profile: ColorProfile): string[] {
  const tags: string[] = []
  if (profile.blueShare > 0.18) tags.push('бассейн', 'вода')
  if (profile.greenShare > 0.18) tags.push('территория', 'зелень')
  if (profile.warmShare > 0.2 && profile.brightShare < 0.35) tags.push('интерьер', 'номер')
  if (profile.brightShare > 0.4 && profile.blueShare < 0.12) tags.push('фасад', 'вид')
  if (tags.length === 0) tags.push('атмосфера')
  return tags
}

export function colorDistance(a: ColorProfile, b: ColorProfile): number {
  return (
    Math.abs(a.meanR - b.meanR) / 255 +
    Math.abs(a.meanG - b.meanG) / 255 +
    Math.abs(a.meanB - b.meanB) / 255 +
    Math.abs(a.blueShare - b.blueShare) +
    Math.abs(a.greenShare - b.greenShare) +
    Math.abs(a.warmShare - b.warmShare)
  )
}
