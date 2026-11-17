import type { NormalizedPoint } from '../types/visualSearch'

function dist2(a: NormalizedPoint, b: NormalizedPoint) {
  const dx = a.x - b.x
  const dy = a.y - b.y
  return dx * dx + dy * dy
}

function perpendicularDistance(point: NormalizedPoint, start: NormalizedPoint, end: NormalizedPoint) {
  const dx = end.x - start.x
  const dy = end.y - start.y
  if (dx === 0 && dy === 0) return Math.sqrt(dist2(point, start))
  const t = ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy)
  const proj = {
    x: start.x + t * dx,
    y: start.y + t * dy,
  }
  return Math.sqrt(dist2(point, proj))
}

function rdp(points: NormalizedPoint[], epsilon: number): NormalizedPoint[] {
  if (points.length <= 2) return points
  let maxDist = 0
  let index = 0
  const end = points.length - 1
  for (let i = 1; i < end; i++) {
    const d = perpendicularDistance(points[i], points[0], points[end])
    if (d > maxDist) {
      maxDist = d
      index = i
    }
  }
  if (maxDist > epsilon) {
    const left = rdp(points.slice(0, index + 1), epsilon)
    const right = rdp(points.slice(index), epsilon)
    return [...left.slice(0, -1), ...right]
  }
  return [points[0], points[end]]
}

/** Light simplification — keeps user shape readable */
export function simplifyPath(points: NormalizedPoint[], epsilon = 0.003): NormalizedPoint[] {
  if (points.length <= 3) return points
  return rdp(points, epsilon)
}
