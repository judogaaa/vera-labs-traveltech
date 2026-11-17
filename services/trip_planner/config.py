from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

USER_AGENT = os.getenv("TRIP_PLANNER_USER_AGENT", "o-hochu-trip-planner/1.0 (vera-labs)")

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org").rstrip("/")

OPENROUTESERVICE_API_KEY = os.getenv("OPENROUTESERVICE_API_KEY", "").strip()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
YANDEX_MAPS_API_KEY = os.getenv("YANDEX_MAPS_API_KEY", "").strip()

# Re-export GigaChat flags from unified AI config
from services.ai import gigachat_config as _gc  # noqa: E402

GIGACHAT_AUTH_KEY = _gc.GIGACHAT_AUTH_KEY
GIGACHAT_CREDENTIALS = GIGACHAT_AUTH_KEY  # back-compat
GIGACHAT_SCOPE = _gc.GIGACHAT_SCOPE
GIGACHAT_MODEL = _gc.GIGACHAT_MODEL
GIGACHAT_AUTH_URL = _gc.GIGACHAT_AUTH_URL
GIGACHAT_API_URL = _gc.GIGACHAT_BASE_URL
GIGACHAT_ENABLED = _gc.GIGACHAT_ENABLED

TRIP_STORE_DIR = Path(os.getenv("TRIP_STORE_DIR", str(_ROOT / "data" / "trips")))
TRIP_STORE_DIR.mkdir(parents=True, exist_ok=True)

PLACES_PROVIDER = os.getenv("TRIP_PLACES_PROVIDER", "overpass").strip().lower()
ROUTING_PROVIDER = os.getenv("TRIP_ROUTING_PROVIDER", "osrm").strip().lower()
GEOCODING_PROVIDER = os.getenv("TRIP_GEOCODING_PROVIDER", "nominatim").strip().lower()

ALLOW_FIXTURE_PROVIDERS = os.getenv("TRIP_ALLOW_FIXTURES", "0").strip() in {"1", "true", "yes"}

HTTP_TIMEOUT = float(os.getenv("TRIP_HTTP_TIMEOUT", "25"))
