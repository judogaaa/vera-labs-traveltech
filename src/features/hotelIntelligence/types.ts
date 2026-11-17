/** Shared types for О!Подбор — mirrors backend /api/hotel-intelligence contracts. */

export type ClaimStatus =
  | 'verified'
  | 'estimated'
  | 'unconfirmed'
  | 'unknown'
  | 'conflicted'
  | 'stale'

export type AttributeScopeKind = 'hotel' | 'building' | 'facade' | 'room_type' | 'room'

export type EvidenceSourceKind =
  | 'osm'
  | 'osrm'
  | 'wikidata'
  | 'official_site'
  | 'public_dataset'
  | 'hotelier'
  | 'hotelier_simulated'
  | 'calculation'

export type AttributeScope = {
  kind: AttributeScopeKind
  identifier?: string | null
}

export type EvidenceSource = {
  kind: EvidenceSourceKind
  uri: string
  fetched_at: string
  published_at?: string | null
}

export type AttributeObservation = {
  observation_id: string
  hotel_id: string
  attribute_key: string
  scope: AttributeScope
  value: unknown
  unit?: string | null
  status: ClaimStatus
  sources: EvidenceSource[]
  confidence?: number | null
  observed_at: string
  valid_until?: string | null
  method: string
  method_version: string
  calculation_inputs?: Record<string, unknown>
}

export type AttributeDefinition = {
  key: string
  description: string
  value_type: string
  needed_tools: string[]
  hotelier_question?: string | null
  ttl_days: number
}

export type IntelligenceHotel = {
  hotel_id: string
  id?: string
  name?: string
  canonical_name?: string
  city?: string
  country?: string
  country_code?: string
  lat?: number | null
  lon?: number | null
  latitude?: number | null
  longitude?: number | null
  region?: string
  zone_key?: string
  official_website?: string
  [key: string]: unknown
}

export type RequestedAttribute = {
  key: string
  role: 'must' | 'should'
  constraint: Record<string, unknown>
}

export type MatchBucketItem = {
  attribute_key: string
  role?: 'must' | 'should'
  value?: unknown
  status?: ClaimStatus | string
  confidence?: number | null
  observation_id?: string
  reason?: string
  detail?: string
  note?: string
  observation_ids?: string[]
}

export type SearchHotelResult = {
  hotel_id: string
  name: string | null
  score: number
  matched: MatchBucketItem[]
  unmatched: MatchBucketItem[]
  unknown: MatchBucketItem[]
  conflicts: MatchBucketItem[]
  explanation?: string | null
}

export type SearchResponse = {
  query: string
  requested: RequestedAttribute[]
  results: SearchHotelResult[]
  extraction?: string
  city?: string | null
  unsupported?: { attribute_key?: string; key?: string; reason?: string }[]
  previous_query?: string | null
  note?: string | null
}

export type IntelligenceStatus = {
  ok: boolean
  db_path?: string
  demo_dir?: string
  demo_mode?: boolean
  hotels: number
  attributes: number
  gigachat_configured?: boolean
}

export type HotelierAnswer = {
  answer_id: string
  question_id: string
  raw_text: string
  source_kind: string
  extraction?: Record<string, unknown>
  created_at: string
}

export type HotelierQuestion = {
  question_id: string
  hotel_id: string
  attribute_key: string
  question_text: string
  status: string
  created_at: string
  scope?: AttributeScope | null
  answers?: HotelierAnswer[]
}

export type ConflictRecord = {
  conflict_id: string
  hotel_id: string
  attribute_key: string
  observation_ids: string[]
  reason: string
  status: string
  created_at?: string
  resolved_at?: string | null
  note?: string | null
  preferred_observation_id?: string | null
}

export type EnrichResponse = {
  run_id: string
  hotel_id: string
  observations: AttributeObservation[]
  questions_created: string[]
  conflicts: unknown[]
  plan: unknown[]
  traces: unknown[]
}

export type HotelIntelligenceApiError = {
  code: string
  message: string
}
