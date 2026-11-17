export type SearchMode = 'full-image' | 'freehand-region' | 'selected-region'

export type NormalizedPoint = {
  x: number
  y: number
}

export type FreehandSelection = {
  points: NormalizedPoint[]
  bounds: {
    x: number
    y: number
    width: number
    height: number
  }
}

/** @deprecated rectangle crop — use FreehandSelection */
export type NormalizedCrop = {
  x: number
  y: number
  width: number
  height: number
}

export type VisualSearchInput = {
  originalFile: File
  originalPreviewUrl: string
  mode: SearchMode
  selection?: FreehandSelection
  selectionMaskBlob?: Blob
  maskedCropBlob?: Blob
  boxedCropBlob?: Blob
  cropPreviewUrl?: string
  featureHints?: string[]
}

export function isRegionSearchMode(mode?: SearchMode) {
  return mode === 'freehand-region' || mode === 'selected-region'
}
