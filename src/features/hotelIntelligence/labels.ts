import type { CatalogHotel } from '../../types/catalog'
import type { ClaimStatus } from './types'

/** Cover URL only from catalog — never invent or swap photos. */
export function catalogCoverUrl(catalogHotel?: CatalogHotel | null): string | null {
  const url = catalogHotel?.images?.[0]
  return typeof url === 'string' && url.trim() ? url : null
}

const ATTRIBUTE_LABELS: Record<string, string> = {
  walk_to_metro: 'Пешком до метро',
  late_night_pharmacy_walk: 'Аптека рядом',
  external_noise_risk: 'Шум снаружи',
  night_services: 'Ночная инфраструктура',
  family_infrastructure: 'Для семьи',
  car_access: 'Доступ на авто',
  blackout_curtains: 'Плотные шторы',
  courtyard_rooms: 'Номера во двор',
  quiet: 'Тишина и шум',
  sunset: 'Вид на закат',
  walkability: 'Пешеходная доступность',
  'night-services': 'Что работает ночью',
  blackout: 'Плотные шторы',
  family: 'Семья и дети',
  pets: 'С питомцами',
  'sea-view': 'Вид на море',
}

const STATUS_LABELS: Record<ClaimStatus | string, string> = {
  verified: 'Проверено',
  estimated: 'Оценка',
  unconfirmed: 'Не подтверждено',
  unknown: 'Неизвестно',
  conflicted: 'Противоречие',
  stale: 'Устарело',
}

const SCOPE_LABELS: Record<string, string> = {
  hotel: 'Отель',
  building: 'Здание',
  facade: 'Фасад',
  room_type: 'Тип номера',
  room: 'Номер',
}

export function attributeLabel(key: string): string {
  return ATTRIBUTE_LABELS[key] ?? key.replace(/_/g, ' ')
}

export function claimStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

export function scopeLabel(kind: string): string {
  return SCOPE_LABELS[kind] ?? kind
}

export function formatObservationValue(key: string, value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  if (typeof value === 'number' || typeof value === 'string') return String(value)

  if (typeof value === 'object' && !Array.isArray(value)) {
    const v = value as Record<string, unknown>
    if (key === 'walk_to_metro') {
      const min =
        v.duration_min ??
        (typeof v.duration_s === 'number' ? Math.round(Number(v.duration_s) / 60) : null)
      if (min != null) return `~${min} мин`
    }
    if (key === 'external_noise_risk' && v.risk != null) {
      const riskMap: Record<string, string> = {
        low: 'низкий риск',
        medium: 'средний риск',
        elevated: 'повышенный риск',
        insufficient_data: 'недостаточно данных',
      }
      return riskMap[String(v.risk)] ?? String(v.risk)
    }
    if (key === 'night_services' && v.late_or_24h_count != null) {
      return `${v.late_or_24h_count} поздних POI`
    }
    if (key === 'family_infrastructure') {
      const p = Number(v.playground_count || 0)
      const parks = Number(v.park_count || 0)
      return `площадки: ${p}, парки: ${parks}`
    }
    if (key === 'car_access') {
      const bits: string[] = []
      if (v.parking_nearby) bits.push('парковка рядом')
      if (v.pedestrian_zone_nearby) bits.push('пешеходная зона')
      return bits.length ? bits.join(', ') : 'нет подсказок'
    }
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

/** Pure helper for why-selected copy — never invents facts beyond API buckets. */
export function whySelectedSummary(input: {
  matched: { attribute_key: string }[]
  unmatched: { attribute_key: string }[]
  unknown: { attribute_key: string }[]
}): string {
  const parts: string[] = []
  if (input.matched.length) {
    parts.push(
      `совпало: ${input.matched.map((m) => attributeLabel(m.attribute_key)).join(', ')}`,
    )
  }
  if (input.unmatched.length) {
    parts.push(
      `не совпало: ${input.unmatched.map((m) => attributeLabel(m.attribute_key)).join(', ')}`,
    )
  }
  if (input.unknown.length) {
    parts.push(
      `неизвестно: ${input.unknown.map((m) => attributeLabel(m.attribute_key)).join(', ')}`,
    )
  }
  if (!parts.length) return 'По этому запросу условий для объяснения нет.'
  return parts.join('; ')
}
