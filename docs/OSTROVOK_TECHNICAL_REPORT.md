# О!Подбор — technical report (Ostrovok track)

## Architecture

Additive module under `services/hotel_intelligence/` and `src/features/hotelIntelligence/`.  
Existing Vera Labs surfaces (visual search, catalog, checkout, О!Маршрут) unchanged aside from nav links and `?hotelId` handoff.

```
User NL query
  → search.parse_query_structured (registry intent_patterns + matchers)
  → IntelligenceStore (SQLite observations)
  → optional Orchestrator.enrich (GeoAgent calculators / HotelierAgent questions)
  → ranked results + explanations (matched / unmatched / unknown / unsupported)
```

Contracts enforce: timezone-aware dates, sources+confidence for stated values, simulated hotelier cannot alone `verified`, append-only conflict visibility.

## Extensibility

Attributes are declarative (`AttributeDefinition`: intent_patterns, matcher, calculator_tool, is_geo).  
Demo extension: `late_night_pharmacy_walk` + `late_night_pharmacy_walk_calc` without editing search core lists.  
Missing tool → honest `unsupported` / `unknown`, not a fake computation.

## Agents

| Agent | Role |
|-------|------|
| ResearchAgent | Which attributes/tools are available via registry |
| GeoAgent | Registry-driven calculators (walk, noise, night, family, car, late pharmacy) |
| HotelierAgent | Questions; multi-scope free-text extract; always simulated in demo |
| VerificationAgent | Per-scope `resolve_observations`, conflict recording |
| Orchestrator | Bounded plan, persist observations, open hotelier gaps |

## Geo methods

- **Walk:** Prefer OSM `subway_entrance` / station nodes; reject metro **line** geometries (`Hattı`, long ways). OSRM **foot**. Else `unknown`.
- **Noise:** density proxy; empty sample → `insufficient_data`, never false `low`.
- **Night / pharmacy:** require opening_hours / confirmed late evidence.
- **Car / family:** parking/park hints only; no silent over-claim.

## Security (demo)

- `HOTEL_INTELLIGENCE_DEMO_MODE` defaults to **off** in code; local `.env.example` enables it explicitly.
- Write routes require matching `X-Write-Token` (`HOTEL_INTELLIGENCE_WRITE_TOKEN`).  
  **`X-Demo-Mutation: 1` alone is rejected (403)** — public frontends cannot escalate.
- `simulated=false` forbidden when demo mode / force_simulated. Bootstrap `demo_dir` cannot escape server config. Enrich rate-limited.
- Evidence DB must live under `HOTEL_INTELLIGENCE_DEMO_DIR` (isolated from curated catalog).

## Local OSM

Calculators prefer `data/ostrovok_demo/osm_local/istanbul_pois.json` when present (`HOTEL_INTELLIGENCE_PREFER_LOCAL_OSM=1`).  
Build: `scripts/build_istanbul_osm_local.py` + optional Nominatim top-up. Attribution ODbL.

## Persistence

SQLite `data/ostrovok_demo/intelligence.sqlite` + jsonl mirrors. Append-only observations; conflicts keep both observation IDs.

## Metrics

| Suite | Purpose | Call it “precision”? |
|-------|---------|----------------------|
| Algorithm↔OSM consistency | Observations ↔ same local OSM snapshot (`build_independent_gold.py`) | **No** — agreement with source data, not search quality |
| API correctness | Auth, schemas, unknown≠match, city filter | No |
| GigaChat extract | Live structured JSON + Pydantic; document examples | Only with defined TP/FP denominator |
| Independent manual / external | Human-reviewed hotel-attribute pairs | Yes, if labels are external to the calculator snapshot |

Artifact: `reports/OSTROVOK_EVAL_LATEST.json` (consistency). Do not report 65/70 as overall hotel-search accuracy.

## Tests

- Backend: `pytest services/hotel_intelligence/tests` (security, extensibility, calculators, search, hotelier)
- Frontend: vitest + Playwright offline smoke / live integration (`e2e/hotel-intelligence.spec.ts`)

## CI

GitHub Actions on PR #24 may fail with empty steps due to **account billing / spending limit**, not application code. Local Verify equivalents are green.
