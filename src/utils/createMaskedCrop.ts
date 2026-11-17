import type { FreehandSelection } from '../types/visualSearch'
import { loadImageElement } from './loadImage'
import { normalizedPointsToPixelPolygon, selectionBoundsFromPoints } from './imageGeometry'

function tracePolygon(
  ctx: CanvasRenderingContext2D,
  points: { x: number; y: number }[],
  offsetX: number,
  offsetY: number,
) {
  ctx.beginPath()
  ctx.moveTo(points[0].x - offsetX, points[0].y - offsetY)
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x - offsetX, points[i].y - offsetY)
  }
  ctx.closePath()
}

export async function createMaskedCrop(
  imageSource: File | Blob | string,
  selection: FreehandSelection,
): Promise<{
  maskedCropBlob: Blob
  boxedCropBlob: Blob
  width: number
  height: number
}> {
  const image = await loadImageElement(imageSource)
  const nw = image.naturalWidth
  const nh = image.naturalHeight
  const polygon = normalizedPointsToPixelPolygon(selection.points, nw, nh)
  const boundsNorm = selection.bounds.width > 0 ? selection.bounds : selectionBoundsFromPoints(selection.points)
  const bx = Math.max(0, Math.floor(boundsNorm.x * nw))
  const by = Math.max(0, Math.floor(boundsNorm.y * nh))
  const bw = Math.max(1, Math.min(Math.ceil(boundsNorm.width * nw), nw - bx))
  const bh = Math.max(1, Math.min(Math.ceil(boundsNorm.height * nh), nh - by))

  const maskedCanvas = document.createElement('canvas')
  maskedCanvas.width = bw
  maskedCanvas.height = bh
  const maskedCtx = maskedCanvas.getContext('2d')
  if (!maskedCtx) throw new Error('Canvas unavailable')

  tracePolygon(maskedCtx, polygon, bx, by)
  maskedCtx.clip()
  maskedCtx.drawImage(image, -bx, -by)

  const boxedCanvas = document.createElement('canvas')
  boxedCanvas.width = bw
  boxedCanvas.height = bh
  const boxedCtx = boxedCanvas.getContext('2d')
  if (!boxedCtx) throw new Error('Canvas unavailable')
  boxedCtx.drawImage(image, bx, by, bw, bh, 0, 0, bw, bh)

  const maskedCropBlob = await canvasToBlob(maskedCanvas, 'image/png')
  const boxedCropBlob = await canvasToBlob(boxedCanvas, 'image/jpeg')

  return { maskedCropBlob, boxedCropBlob, width: bw, height: bh }
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('Export failed'))),
      type,
      type === 'image/jpeg' ? 0.92 : undefined,
    )
  })
}
