import type { NormalizedPoint } from '../types/visualSearch'
import { normalizedPointsToPixelPolygon } from './imageGeometry'

export async function createSelectionMask(
  width: number,
  height: number,
  points: NormalizedPoint[],
): Promise<Blob> {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas unavailable')

  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, width, height)

  const polygon = normalizedPointsToPixelPolygon(points, width, height)
  if (polygon.length < 3) throw new Error('Invalid selection')

  ctx.beginPath()
  ctx.moveTo(polygon[0].x, polygon[0].y)
  for (let i = 1; i < polygon.length; i++) {
    ctx.lineTo(polygon[i].x, polygon[i].y)
  }
  ctx.closePath()
  ctx.fillStyle = '#ffffff'
  ctx.fill()

  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob((result) => resolve(result), 'image/png')
  })
  if (!blob) throw new Error('Не удалось создать mask')
  return blob
}
