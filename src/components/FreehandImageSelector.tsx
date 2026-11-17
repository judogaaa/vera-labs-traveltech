import { useCallback, useEffect, useRef, useState } from 'react'
import type { FreehandSelection, NormalizedPoint } from '../types/visualSearch'
import {
  isSelectionLargeEnough,
  localPointToNormalized,
  pathDFromPoints,
  selectionBoundsFromPoints,
  type LocalImageBounds,
} from '../utils/imageGeometry'
import { simplifyPath } from '../utils/simplifyPath'

const MIN_POINTS = 8

type FreehandImageSelectorProps = {
  imageUrl: string
  selection: FreehandSelection | null
  onSelectionChange: (selection: FreehandSelection | null) => void
  onHelper?: (message: string | null) => void
  disabled?: boolean
}

/** Bounds = the painted image box inside the container (img is sized to content). */
function measureImageBounds(img: HTMLImageElement, container: HTMLElement): LocalImageBounds {
  const c = container.getBoundingClientRect()
  const i = img.getBoundingClientRect()
  return {
    left: i.left - c.left,
    top: i.top - c.top,
    width: Math.max(1, i.width),
    height: Math.max(1, i.height),
    naturalWidth: img.naturalWidth || 1,
    naturalHeight: img.naturalHeight || 1,
  }
}

export function FreehandImageSelector({
  imageUrl,
  selection,
  onSelectionChange,
  onHelper,
  disabled = false,
}: FreehandImageSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const imageRef = useRef<HTMLImageElement>(null)
  const boundsRef = useRef<LocalImageBounds | null>(null)
  const drawingRef = useRef(false)
  const lastPointRef = useRef<NormalizedPoint | null>(null)
  const draftRef = useRef<NormalizedPoint[] | null>(null)

  const [ready, setReady] = useState(false)
  const [error, setError] = useState(false)
  const [draftPoints, setDraftPoints] = useState<NormalizedPoint[] | null>(null)
  const [showHint, setShowHint] = useState(true)
  const [bounds, setBounds] = useState<LocalImageBounds | null>(null)
  const [surfaceSize, setSurfaceSize] = useState({ width: 0, height: 0 })

  const refreshBounds = useCallback(() => {
    if (drawingRef.current) return boundsRef.current
    const img = imageRef.current
    const container = containerRef.current
    if (!img || !container || !img.naturalWidth) return null

    const next = measureImageBounds(img, container)
    boundsRef.current = next
    setBounds(next)

    const rect = container.getBoundingClientRect()
    setSurfaceSize({
      width: Math.max(1, rect.width),
      height: Math.max(1, rect.height),
    })
    return next
  }, [])

  useEffect(() => {
    setReady(false)
    setError(false)
    setDraftPoints(null)
    draftRef.current = null
    setShowHint(true)
    setBounds(null)
    setSurfaceSize({ width: 0, height: 0 })
    boundsRef.current = null
  }, [imageUrl])

  useEffect(() => {
    const onResize = () => refreshBounds()
    window.addEventListener('resize', onResize)
    const node = containerRef.current
    const ro = typeof ResizeObserver !== 'undefined' && node ? new ResizeObserver(() => refreshBounds()) : null
    if (node && ro) ro.observe(node)
    return () => {
      window.removeEventListener('resize', onResize)
      ro?.disconnect()
    }
  }, [refreshBounds, ready])

  const isInsideImage = (clientX: number, clientY: number, localBounds: LocalImageBounds) => {
    const container = containerRef.current
    if (!container) return false
    const rect = container.getBoundingClientRect()
    const localX = clientX - rect.left
    const localY = clientY - rect.top
    return (
      localX >= localBounds.left &&
      localY >= localBounds.top &&
      localX <= localBounds.left + localBounds.width &&
      localY <= localBounds.top + localBounds.height
    )
  }

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (disabled || !ready || error) return
    const nextBounds = refreshBounds()
    const container = containerRef.current
    if (!nextBounds || !container) return
    if (!isInsideImage(e.clientX, e.clientY, nextBounds)) return

    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    setShowHint(false)
    onHelper?.(null)
    drawingRef.current = true
    onSelectionChange(null)

    const point = localPointToNormalized(e.clientX, e.clientY, container, nextBounds)
    lastPointRef.current = point
    draftRef.current = [point]
    setDraftPoints([point])
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drawingRef.current) return
    const currentBounds = boundsRef.current
    const container = containerRef.current
    const last = lastPointRef.current
    if (!currentBounds || !container || !last) return

    e.preventDefault()
    const point = localPointToNormalized(e.clientX, e.clientY, container, currentBounds)
    const dx = (point.x - last.x) * currentBounds.width
    const dy = (point.y - last.y) * currentBounds.height
    if (Math.hypot(dx, dy) < 2) return

    lastPointRef.current = point
    const next = [...(draftRef.current ?? []), point]
    draftRef.current = next
    setDraftPoints(next)
  }

  const finishStroke = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drawingRef.current) return
    drawingRef.current = false
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch {
      // ignore
    }

    const currentBounds = boundsRef.current
    const current = draftRef.current
    draftRef.current = null
    setDraftPoints(null)
    if (!currentBounds || !current || current.length < MIN_POINTS) {
      onHelper?.('Обведите область немного крупнее')
      lastPointRef.current = null
      return
    }

    const simplified = simplifyPath(current)
    const closed = simplified.length >= 3 ? simplified : current
    const selectionBounds = selectionBoundsFromPoints(closed)

    if (!isSelectionLargeEnough(selectionBounds, currentBounds)) {
      onHelper?.('Обведите область немного крупнее')
      lastPointRef.current = null
      return
    }

    onSelectionChange({ points: closed, bounds: selectionBounds })
    lastPointRef.current = null
    requestAnimationFrame(() => refreshBounds())
  }

  const activePoints = draftPoints ?? selection?.points ?? null
  const isDrawing = Boolean(draftPoints)
  const hasClosedSelection = Boolean(selection && !draftPoints)

  const strokePath =
    bounds && activePoints ? pathDFromPoints(activePoints, bounds, !isDrawing && hasClosedSelection) : ''

  const dimPath =
    bounds && hasClosedSelection && selection && surfaceSize.width > 0
      ? `M 0 0 H ${surfaceSize.width} V ${surfaceSize.height} H 0 Z ${pathDFromPoints(selection.points, bounds, true)}`
      : ''

  const badgePos =
    hasClosedSelection && selection && bounds
      ? {
          left: bounds.left + selection.bounds.x * bounds.width,
          top: Math.max(8, bounds.top + selection.bounds.y * bounds.height - 28),
        }
      : null

  return (
    <div className="overflow-hidden rounded-2xl bg-surface-muted ring-1 ring-border/80">
      <div
        ref={containerRef}
        className="relative mx-auto w-fit max-w-full touch-none select-none"
        style={{ touchAction: 'none' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finishStroke}
        onPointerCancel={finishStroke}
        role="application"
        aria-describedby="freehand-selection-hint"
        aria-label="Обведите деталь на фото"
      >
        {!ready && !error ? (
          <div className="aspect-[16/10] w-[min(100%,720px)] animate-pulse bg-surface-muted" />
        ) : null}
        {error ? (
          <div className="flex min-h-40 items-center justify-center px-6 py-10 text-center text-sm text-text-secondary">
            Не удалось открыть изображение. Попробуйте другой файл.
          </div>
        ) : (
          <img
            ref={imageRef}
            src={imageUrl}
            alt="Фото для обводки детали"
            className="block max-h-[min(72vh,720px)] max-w-full h-auto w-auto"
            draggable={false}
            onLoad={() => {
              setReady(true)
              requestAnimationFrame(() => refreshBounds())
            }}
            onError={() => setError(true)}
          />
        )}

        {ready && bounds && surfaceSize.width > 0 ? (
          <svg
            className="pointer-events-none absolute inset-0"
            width={surfaceSize.width}
            height={surfaceSize.height}
            viewBox={`0 0 ${surfaceSize.width} ${surfaceSize.height}`}
            aria-hidden
          >
            {hasClosedSelection && dimPath ? (
              <path
                d={dimPath}
                fill="rgba(10, 18, 60, 0.26)"
                fillRule="evenodd"
                className="freehand-dim"
              />
            ) : null}
            {strokePath ? (
              <>
                <path
                  d={strokePath}
                  fill="none"
                  stroke="rgba(255,255,255,0.95)"
                  strokeWidth={5.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
                <path
                  d={strokePath}
                  fill={hasClosedSelection ? 'rgba(255,255,255,0.03)' : 'none'}
                  stroke="#0e41d2"
                  strokeWidth={2.75}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
              </>
            ) : null}
          </svg>
        ) : null}

        {badgePos ? (
          <span
            className="pointer-events-none absolute z-10 rounded-full bg-white/95 px-2.5 py-1 text-[11px] font-semibold text-brand-blue-950 shadow-sm"
            style={{ left: badgePos.left, top: badgePos.top }}
          >
            Обведено
          </span>
        ) : null}

        {showHint && ready && !selection && !draftPoints ? (
          <div className="pointer-events-none absolute inset-x-3 bottom-3 z-10 rounded-xl bg-white/94 px-3.5 py-2.5 text-center text-[13px] font-medium text-brand-blue-950 shadow-sm sm:inset-x-4 sm:bottom-4 sm:px-4 sm:py-3 sm:text-sm">
            <span id="freehand-selection-hint">Проведите пальцем вокруг нужной детали</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}
