# О!Маршрут — architecture

## Flow

```
User → TripPlannerAgent → GigaChat (orchestration / function calling)
                       → PlacesProvider / GeocodingProvider / RoutingProvider
                       → itinerary optimizer → Trip JSON → MapLibre + timeline + PDF
```

GigaChat **never** invents POIs, coordinates, distances, times, or ratings.
All facts come from providers; the model only chooses tools and explains results.

## Backend modules

| Path | Role |
|------|------|
| `services/ai/*` | Unified GigaChat client + token manager |
| `services/trip_planner/agent.py` | Plan / chat / stream |
| `services/trip_planner/tools.py` | User-defined functions for GigaChat |
| `services/trip_planner/providers/*` | Nominatim, Overpass, OSRM (swappable) |
| `services/trip_planner/optimizer.py` | Clustering, day timeline, verified routes |
| `services/trip_planner/pdf.py` | Cyrillic PDF export |
| `services/trip_planner/api.py` | FastAPI routes mounted in `search_api` |
| `prompts/trip_planner_system_v1.md` | Versioned system prompt |

## Providers (MVP defaults)

- **Geocoding:** Nominatim
- **Places:** Overpass (OSM)
- **Routing:** Public OSRM
- **Map tiles (frontend):** OpenStreetMap raster via MapLibre GL

No silent fake itinerary in production. Fixtures only for unit tests / explicit `TRIP_ALLOW_FIXTURES`.

## API

- `POST /api/trips/plan` (+ `/stream` SSE)
- `POST /api/trips/{id}/chat`
- `GET|PATCH|DELETE /api/trips/{id}`
- `GET /api/trips/{id}/pdf`
- `POST /api/places/search`, `POST /api/routes/calculate`
- `GET /api/trips/status`

## Frontend

- Route: `/oh-route`
- Split chat | map/trip (desktop); tabs on mobile
- Hotel CTA → query context (`hotelId`, coords, city)
- Persistence: `localStorage` key `ohotchu.plannedTrips` + backend JSON store
- Dev panel: `?dev=1`
