export function createObjectUrl(source: Blob | MediaSource): string {
  return URL.createObjectURL(source)
}

export function revokeObjectUrl(url?: string | null) {
  if (!url) return
  if (url.startsWith('blob:')) {
    try {
      URL.revokeObjectURL(url)
    } catch {
      // ignore
    }
  }
}

export function replaceObjectUrl(prev: string | null | undefined, nextSource?: Blob | null) {
  revokeObjectUrl(prev)
  if (!nextSource) return null
  return createObjectUrl(nextSource)
}
