export async function loadImageElement(source: string | Blob): Promise<HTMLImageElement> {
  if (typeof createImageBitmap === 'function' && typeof source !== 'string') {
    try {
      const bitmap = await createImageBitmap(source)
      const canvas = document.createElement('canvas')
      canvas.width = bitmap.width
      canvas.height = bitmap.height
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('Canvas unavailable')
      ctx.drawImage(bitmap, 0, 0)
      bitmap.close()
      return loadFromUrl(canvas.toDataURL())
    } catch {
      // fallback
    }
  }

  const url = typeof source === 'string' ? source : URL.createObjectURL(source)
  try {
    return await loadFromUrl(url)
  } finally {
    if (typeof source !== 'string') URL.revokeObjectURL(url)
  }
}

function loadFromUrl(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.decoding = 'async'
    img.onload = async () => {
      try {
        if (img.decode) await img.decode()
      } catch {
        // ignore
      }
      resolve(img)
    }
    img.onerror = () => reject(new Error('Не удалось открыть изображение'))
    img.src = url
  })
}
