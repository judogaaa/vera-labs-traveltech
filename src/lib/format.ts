export function formatPrice(value: number): string {
  if (!Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('ru-RU').format(value)
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`
}

export function formatReviews(count: number): string {
  const mod10 = count % 10
  const mod100 = count % 100
  let word = 'отзывов'
  if (mod10 === 1 && mod100 !== 11) word = 'отзыв'
  else if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) word = 'отзыва'
  return `${formatPrice(count)} ${word}`
}

export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const MAX_FILE_SIZE = 10 * 1024 * 1024

export function validateImageFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return 'Поддерживаются только JPG, PNG и WEBP'
  }
  if (file.size > MAX_FILE_SIZE) {
    return 'Файл слишком большой — максимум 10 МБ'
  }
  return null
}
