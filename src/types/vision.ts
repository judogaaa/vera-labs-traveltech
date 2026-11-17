export type VisualAnalysis = {
  visualTags: string[]
  inferredEnvironment: string[]
  possibleText: string[]
  detectedFeatures: string[]
  /** GigaChat Vision assist (never replaces identity match). */
  gigachatAssist?: {
    features: string[]
    refinedQuery?: string | null
    visionInvoked: boolean
    model?: string | null
    limitation?: string | null
  }
}

export type HotelMatchLevel = 'very-high' | 'high' | 'possible'

export type HotelMatch = {
  hotelId: string
  matchLevel: HotelMatchLevel
  matchedFeatures: string[]
  isExactCandidate: boolean
  matchedImageUrl?: string
  score?: number
  /** Present for cloud/Qdrant hits not in the local demo catalog */
  hotelName?: string
  chain?: string
  latitude?: number
  longitude?: number
  source?: 'cloud' | 'local' | 'mock'
}

export type MatchScenario = 'exact' | 'multiple' | 'none' | 'region'
