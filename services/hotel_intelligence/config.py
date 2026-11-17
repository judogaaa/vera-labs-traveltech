"""Paths and env for the hotel-intelligence addon (isolated from visual search)."""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

DEMO_DIR = Path(
    os.getenv("HOTEL_INTELLIGENCE_DEMO_DIR", str(_ROOT / "data" / "ostrovok_demo"))
).resolve()
DB_PATH = Path(
    os.getenv(
        "HOTEL_INTELLIGENCE_DB",
        str(DEMO_DIR / "intelligence.sqlite"),
    )
).resolve()
CACHE_DIR = DEMO_DIR / "cache"
OSM_LOCAL_DIR = DEMO_DIR / "osm_local"
OSM_LOCAL_INDEX = OSM_LOCAL_DIR / "istanbul_pois.json"

OSM_TIMEOUT_S = float(os.getenv("HOTEL_INTELLIGENCE_OSM_TIMEOUT", "25"))
OVERPASS_URL = os.getenv(
    "OVERPASS_URL", "https://overpass-api.de/api/interpreter"
).rstrip("/")
OVERPASS_MIRRORS = [
    u.strip().rstrip("/")
    for u in os.getenv(
        "OVERPASS_MIRRORS",
        ",".join(
            [
                OVERPASS_URL,
                "https://overpass.kumi.systems/api/interpreter",
                "https://overpass.openstreetmap.ru/api/interpreter",
            ]
        ),
    ).split(",")
    if u.strip()
]
NOMINATIM_URL = os.getenv(
    "NOMINATIM_URL", "https://nominatim.openstreetmap.org"
).rstrip("/")
USER_AGENT = os.getenv(
    "HOTEL_INTELLIGENCE_USER_AGENT",
    "vera-labs-hotel-intelligence/0.1 (demo; contact: local)",
)

# Security: demo-mode OFF by default outside explicit local .env
# Local .env.example sets HOTEL_INTELLIGENCE_DEMO_MODE=1 + WRITE_TOKEN.
DEMO_MODE = os.getenv("HOTEL_INTELLIGENCE_DEMO_MODE", "0").strip() in {
    "1",
    "true",
    "True",
    "yes",
    "YES",
}
HOTEL_INTELLIGENCE_WRITE_TOKEN = os.getenv("HOTEL_INTELLIGENCE_WRITE_TOKEN", "").strip()
HOTEL_INTELLIGENCE_ENRICH_MAX_PER_MIN = int(
    os.getenv("HOTEL_INTELLIGENCE_ENRICH_MAX_PER_MIN", "10")
)
# Prefer local OSM snapshot for calculators when present
HOTEL_INTELLIGENCE_PREFER_LOCAL_OSM = os.getenv(
    "HOTEL_INTELLIGENCE_PREFER_LOCAL_OSM", "1"
).strip() in {"1", "true", "True", "yes", "YES"}


def assert_db_isolated() -> None:
    """Demo mutations must stay under DEMO_DIR (no production catalog paths)."""
    try:
        DB_PATH.relative_to(DEMO_DIR)
    except ValueError as exc:
        raise RuntimeError(
            f"HOTEL_INTELLIGENCE_DB must be under DEMO_DIR ({DEMO_DIR}); got {DB_PATH}"
        ) from exc
