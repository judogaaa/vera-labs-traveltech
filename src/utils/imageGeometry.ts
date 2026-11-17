import type { NormalizedPoint } from '../types/visualSearch'

export type RenderedImageBounds = {
  left: number
  top: number
  width: number
  height: number
  naturalWidth: number
  naturalHeight: number
}

export type LocalImageBounds = Omit<RenderedImageBounds, 'naturalWidth' | 'naturalHeight'> & {
  naturalWidth: number
  naturalHeight: number
}

/** object-fit: contain — bounds relative to container element */
export function getLocalImageBounds(
  img: HTMLImageElement,
  container: HTMLElement,
): LocalImageBounds {
  const containerRect = container.getBoundingClientRect()
  const naturalWidth = img.naturalWidth || 1
  const naturalHeight = img.naturalHeight || 1
  const elementRatio = containerRect.width / Math.max(containerRect.height, 1)
  const imageRatio = naturalWidth / naturalHeight

  let width = containerRect.width
  let height = containerRect.height
  let left = 0
  let top = 0

  if (elementRatio > imageRatio) {
    height = containerRect.height
    width = height * imageRatio
    left = (containerRect.width - width) / 2
    top = 0
  } else {
    width = containerRect.width
    height = width / imageRatio
    left = 0
    top = (containerRect.height - height) / 2
  }

  return { left, top, width, height, naturalWidth, naturalHeight }
}

export function getRenderedImageBounds(img: HTMLImageElement): RenderedImageBounds {
  const rect = img.getBoundingClientRect()
  const naturalWidth = img.naturalWidth || 1
  const naturalHeight = img.naturalHeight || 1
  const elementRatio = rect.width / Math.max(rect.height, 1)
  const imageRatio = naturalWidth / naturalHeight

  let width = rect.width
  let height = rect.height
  let left = rect.left
  let top = rect.top

  if (elementRatio > imageRatio) {
    height = rect.height
    width = height * imageRatio
    left = rect.left + (rect.width - width) / 2
    top = rect.top
  } else {
    width = rect.width
    height = width / imageRatio
    left = rect.left
    top = rect.top + (rect.height - height) / 2
  }

  return { left, top, width, height, naturalWidth, naturalHeight }
}

export function localPointToNormalized(
  clientX: number,
  clientY: number,
  container: HTMLElement,
  bounds: LocalImageBounds,
): NormalizedPoint {
  const rect = container.getBoundingClientRect()
  const x = (clientX - rect.left - bounds.left) / Math.max(bounds.width, 1)
  const y = (clientY - rect.top - bounds.top) / Math.max(bounds.height, 1)
  return { x: clamp01(x), y: clamp01(y) }
}

export function screenPointToNormalizedImagePoint(
  clientX: number,
  clientY: number,
  bounds: RenderedImageBounds,
): NormalizedPoint {
  const x = (clientX - bounds.left) / Math.max(bounds.width, 1)
  const y = (clientY - bounds.top) / Math.max(bounds.height, 1)
  return { x: clamp01(x), y: clamp01(y) }
}

export function normalizedPointToLocalPoint(
  point: NormalizedPoint,
  bounds: LocalImageBounds,
): { x: number; y: number } {
  return {
    x: bounds.left + point.x * bounds.width,
    y: bounds.top + point.y * bounds.height,
  }
}

export function selectionBoundsFromPoints(points: NormalizedPoint[]) {
  if (points.length === 0) {
    return { x: 0, y: 0, width: 0, height: 0 }
  }
  let minX = 1
  let minY = 1
  let maxX = 0
  let maxY = 0
  for (const p of points) {
    minX = Math.min(minX, p.x)
    minY = Math.min(minY, p.y)
    maxX = Math.max(maxX, p.x)
    maxY = Math.max(maxY, p.y)
  }
  return {
    x: minX,
    y: minY,
    width: Math.max(0, maxX - minX),
    height: Math.max(0, maxY - minY),
  }
}

export function normalizedPointsToPixelPolygon(
  points: NormalizedPoint[],
  naturalWidth: number,
  naturalHeight: number,
) {
  return points.map((p) => ({
    x: clamp01(p.x) * naturalWidth,
    y: clamp01(p.y) * naturalHeight,
  }))
}

export function normalizedCropToPixelCrop(
  crop: { x: number; y: number; width: number; height: number },
  naturalWidth: number,
  naturalHeight: number,
) {
  const x = Math.round(clamp01(crop.x) * naturalWidth)
  const y = Math.round(clamp01(crop.y) * naturalHeight)
  const width = Math.max(1, Math.round(clamp01(crop.width) * naturalWidth))
  const height = Math.max(1, Math.round(clamp01(crop.height) * naturalHeight))
  return {
    x: Math.min(x, naturalWidth - 1),
    y: Math.min(y, naturalHeight - 1),
    width: Math.min(width, naturalWidth - x),
    height: Math.min(height, naturalHeight - y),
  }
}

export function clamp01(value: number) {
  return Math.min(1, Math.max(0, value))
}

export function isSelectionLargeEnough(
  bounds: { width: number; height: number },
  imageBounds: LocalImageBounds,
  minPx = 40,
) {
  const w = bounds.width * imageBounds.width
  const h = bounds.height * imageBounds.height
  // Accept if both sides are large enough, or the area is clearly intentional.
  return (w >= minPx && h >= minPx) || w * h >= minPx * minPx * 1.5
}

export function pathDFromPoints(
  points: NormalizedPoint[],
  bounds: LocalImageBounds,
  close = false,
) {
  if (points.length === 0) return ''
  const first = normalizedPointToLocalPoint(points[0], bounds)
  let d = `M ${first.x} ${first.y}`
  for (let i = 1; i < points.length; i++) {
    const p = normalizedPointToLocalPoint(points[i], bounds)
    d += ` L ${p.x} ${p.y}`
  }
  if (close) d += ' Z'
  return d
}
