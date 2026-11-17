"""Resolve verified landmark photos from OSM Commons / Wikidata P18.

Never invent city-stock photos. Cache resolved HTTPS thumbnails on disk.
Hard wall-clock budgets — external failures never hang trip/PDF generation.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from pathlib import Path

from .models import Place, Stop, Trip

UA = "OhHochu-TripPlanner/1.0 (https://github.com/judogaaa/vera-labs; educational)"
CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "trip_photos_cache.json"
THUMB_WIDTH = 640
PDF_WIDTH = 960
MAX_IMAGE_BYTES = 3_500_000
_LOCK = threading.Lock()
_memory: dict[str, str | None] = {}
# In-flight HTTP budget per process (shared across enrich calls)
_HTTP_DEADLINE = threading.local()

_WD_RE = re.compile(r"^Q\d+$", re.I)
_ALLOWED_HOST_FRAGMENTS = (
    "wikimedia.org",
    "wikipedia.org",
    "upload.wikimedia.org",
    "commons.wikimedia.org",
)


def commons_file_url(title: str, width: int = THUMB_WIDTH) -> str | None:
    """Build a Commons Special:FilePath URL for a File: title or bare filename."""
    raw = (title or "").strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        url = raw.replace("http://", "https://", 1)
        if "Special:FilePath/" in url and "width=" not in url:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}width={width}"
        return url
    if raw.lower().startswith("category:"):
        return None
    name = raw
    if name.lower().startswith("file:"):
        name = name[5:]
    name = name.replace("_", " ").strip()
    if not name:
        return None
    quoted = urllib.parse.quote(name)
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quoted}?width={width}"


def _load_cache() -> dict[str, str | None]:
    if _memory:
        return _memory
    with _LOCK:
        if _memory:
            return _memory
        if CACHE_PATH.exists():
            try:
                data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _memory.update(
                        {
                            str(k): (v if isinstance(v, str) or v is None else None)
                            for k, v in data.items()
                        }
                    )
            except (OSError, json.JSONDecodeError):
                pass
        return _memory


def _save_cache() -> None:
    with _LOCK:
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            items = list(_memory.items())
            if len(items) > 4000:
                items = items[-4000:]
                _memory.clear()
                _memory.update(items)
            CACHE_PATH.write_text(json.dumps(dict(items), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def _remaining_budget() -> float:
    deadline = getattr(_HTTP_DEADLINE, "deadline", None)
    if deadline is None:
        return 6.0
    return max(0.05, deadline - time.perf_counter())


def _http_get_json(url: str, timeout: float | None = None) -> dict | None:
    t = min(timeout if timeout is not None else 4.0, _remaining_budget())
    if t <= 0.05:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=t) as resp:
            raw = resp.read(MAX_IMAGE_BYTES + 1)
            if len(raw) > MAX_IMAGE_BYTES:
                return None
            return json.loads(raw.decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
        return None


def _trusted_image_url(url: str) -> bool:
    """Only fetch verified Wikimedia image hosts, never arbitrary OSM/image URLs.

    Downloading unchecked user-supplied HTTPS links could reach internal services
    (including via a redirect) when the trip PDF is rendered by the API.
    Other external image refs may still be shown in the browser as links.
    """
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        return (
            parts.scheme == "https"
            and bool(host)
            and parts.username is None
            and parts.password is None
            and parts.port in (None, 443)
            and (host == "wikimedia.org" or host.endswith(".wikimedia.org")
                 or host == "wikipedia.org" or host.endswith(".wikipedia.org"))
        )
    except ValueError:
        return False


class _SafeImageRedirect(urllib.request.HTTPRedirectHandler):
    """Deny redirect chains from trusted Wikimedia hosts to other networks."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        if not _trusted_image_url(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_image_bytes(url: str, *, timeout: float | None = None, max_bytes: int = MAX_IMAGE_BYTES) -> bytes | None:
    """Safe HTTPS image download with size cap and budget-aware timeout."""
    if not url or not _trusted_image_url(str(url)):
        return None
    host = urllib.parse.urlsplit(url).hostname or ""
    # Strict host allowlist also applies to redirects, not only the initial URL.
    t = min(timeout if timeout is not None else 5.0, _remaining_budget())
    if t <= 0.05:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,*/*"})
    try:
        with urllib.request.build_opener(_SafeImageRedirect()).open(req, timeout=t) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if ctype and not any(x in ctype for x in ("image/", "octet-stream", "binary")):
                # Still allow if Commons redirects oddly
                if "wikimedia" not in host and "wikipedia" not in host:
                    return None
            data = resp.read(max_bytes + 1)
            if len(data) < 200 or len(data) > max_bytes:
                return None
            return data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def commons_attribution(file_title_or_url: str, *, timeout: float = 3.0) -> str | None:
    """Best-effort author/license line from Commons imageinfo (never blocks long)."""
    raw = (file_title_or_url or "").strip()
    if not raw:
        return None
    title = raw
    if "Special:FilePath/" in raw:
        title = urllib.parse.unquote(raw.split("Special:FilePath/", 1)[1].split("?", 1)[0])
    if title.lower().startswith("file:"):
        title = title[5:]
    title = f"File:{title.replace('_', ' ').strip()}"
    cache_key = f"attr:{title}"
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    params = urllib.parse.urlencode(
        {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "extmetadata|user",
            "format": "json",
        }
    )
    payload = _http_get_json(f"https://commons.wikimedia.org/w/api.php?{params}", timeout=timeout)
    line: str | None = None
    try:
        pages = (payload or {}).get("query", {}).get("pages", {})
        for page in pages.values():
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            meta = infos[0].get("extmetadata") or {}
            artist = (meta.get("Artist") or {}).get("value") or infos[0].get("user") or ""
            license_ = (meta.get("LicenseShortName") or {}).get("value") or ""
            # Strip HTML tags from Artist
            artist = re.sub(r"<[^>]+>", "", str(artist)).strip()
            bits = [b for b in (artist[:80], license_) if b]
            if bits:
                line = " · ".join(bits) + " · Wikimedia Commons"
            else:
                line = "Wikimedia Commons"
            break
    except (AttributeError, TypeError, KeyError):
        line = None
    cache[cache_key] = line
    _save_cache()
    return line


def wikidata_p18_url(qid: str, width: int = THUMB_WIDTH) -> str | None:
    """Fetch Wikidata P18 (image) for Q-id and return Commons FilePath URL.

    Note: Wikidata P18 is occasionally wrong/outdated; callers may prefer an
    explicit Commons File: title when they have a verified one.
    """
    q = (qid or "").strip()
    if q.startswith("http"):
        q = q.rsplit("/", 1)[-1]
    if not _WD_RE.match(q):
        return None
    cache_key = f"wd:{q.upper()}:w{width}"
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    params = urllib.parse.urlencode(
        {
            "action": "wbgetentities",
            "ids": q.upper(),
            "props": "claims",
            "format": "json",
        }
    )
    url = f"https://www.wikidata.org/w/api.php?{params}"
    payload = _http_get_json(url)
    resolved: str | None = None
    try:
        entity = (payload or {}).get("entities", {}).get(q.upper(), {})
        claims = (entity.get("claims") or {}).get("P18") or []
        if claims:
            mainsnak = claims[0].get("mainsnak") or {}
            datavalue = mainsnak.get("datavalue") or {}
            filename = datavalue.get("value")
            if isinstance(filename, str) and filename:
                candidate = commons_file_url(filename, width=width)
                # Probe that the file actually downloads (guards broken/wrong P18)
                if candidate and fetch_image_bytes(candidate, timeout=min(3.0, _remaining_budget())):
                    resolved = candidate
    except (AttributeError, IndexError, TypeError, KeyError):
        resolved = None

    cache[cache_key] = resolved
    _save_cache()
    return resolved


def resolve_photo_ref(
    photo_ref: str | None,
    wikidata_id: str | None = None,
    *,
    width: int = THUMB_WIDTH,
) -> str | None:
    """Resolve OSM image / commons / wikidata into a verified HTTPS thumbnail URL."""
    cache = _load_cache()
    ref = (photo_ref or "").strip() or None
    wd = (wikidata_id or "").strip() or None
    cache_key = f"ref:{(ref or '')}|{(wd or '')}:w{width}"
    if cache_key in cache:
        return cache[cache_key]

    resolved: str | None = None
    # Prefer explicit Commons/OSM image refs over Wikidata P18 (P18 can be wrong).
    if ref:
        if ref.startswith("http://") or ref.startswith("https://"):
            host = urllib.parse.urlparse(ref).netloc.lower()
            if any(h in host for h in _ALLOWED_HOST_FRAGMENTS):
                resolved = commons_file_url(ref, width=width)
            elif ref.startswith("https://"):
                resolved = ref
        else:
            resolved = commons_file_url(ref, width=width)

    if not resolved and wd:
        resolved = wikidata_p18_url(wd, width=width)

    cache[cache_key] = resolved
    _save_cache()
    return resolved


def enrich_place(place: Place, *, width: int = THUMB_WIDTH) -> Place:
    wd = getattr(place, "wikidataId", None)
    url = resolve_photo_ref(place.photoUrl, wd, width=width)
    if url and url != place.photoUrl:
        return place.model_copy(update={"photoUrl": url})
    if url is None and place.photoUrl and not str(place.photoUrl).startswith("http"):
        return place.model_copy(update={"photoUrl": None})
    return place


def enrich_places(places: list[Place], *, width: int = THUMB_WIDTH, timeout_s: float = 4.0) -> list[Place]:
    """Resolve photos in parallel with a hard wall-clock budget (never hangs)."""
    if not places:
        return places
    out = list(places)
    deadline = time.perf_counter() + max(0.2, timeout_s)
    _HTTP_DEADLINE.deadline = deadline

    def _one(idx: int, p: Place) -> tuple[int, Place]:
        _HTTP_DEADLINE.deadline = deadline
        return idx, enrich_place(p, width=width)

    executor = ThreadPoolExecutor(max_workers=min(6, max(1, len(places))))
    try:
        futures = {executor.submit(_one, i, p): i for i, p in enumerate(places)}
        remaining = max(0.1, deadline - time.perf_counter())
        try:
            for fut in as_completed(futures, timeout=remaining):
                if time.perf_counter() >= deadline:
                    break
                try:
                    idx, enriched = fut.result(timeout=0.05)
                    out[idx] = enriched
                except Exception:  # noqa: BLE001
                    continue
        except FuturesTimeout:
            pass
    finally:
        # Do not wait forever for stuck HTTP — abandon workers.
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)
        _HTTP_DEADLINE.deadline = None

    cleaned: list[Place] = []
    for p in out:
        if p.photoUrl and not str(p.photoUrl).startswith("http"):
            cleaned.append(p.model_copy(update={"photoUrl": None}))
        else:
            cleaned.append(p)
    return cleaned


def enrich_trip_photos(trip: Trip, *, width: int = THUMB_WIDTH, timeout_s: float = 5.0) -> Trip:
    """Fill stop.photoUrl from Commons/Wikidata for all days (best-effort)."""
    stops: list[Stop] = [s for d in trip.days for s in d.stops]
    if not stops:
        return trip

    places = [
        Place(
            placeProvider=s.placeProvider,
            placeId=s.placeId,
            name=s.name,
            category=s.category,
            lat=s.lat,
            lon=s.lon,
            address=s.address,
            description=s.description,
            photoUrl=s.photoUrl,
            rating=s.rating,
            ratingCount=s.ratingCount,
            website=s.website,
            wikidataId=getattr(s, "wikidataId", None),
        )
        for s in stops
    ]
    enriched = enrich_places(places, width=width, timeout_s=timeout_s)
    by_id = {p.placeId: p.photoUrl for p in enriched}

    new_days = []
    for day in trip.days:
        new_stops = []
        for s in day.stops:
            url = by_id.get(s.placeId, s.photoUrl)
            if url and not str(url).startswith("http"):
                url = None
            new_stops.append(s.model_copy(update={"photoUrl": url}))
        new_days.append(day.model_copy(update={"stops": new_stops}))
    return trip.model_copy(update={"days": new_days})


def maps_link(lat: float, lon: float, name: str = "") -> str:
    """OpenStreetMap marker link for a single point (not turn-by-turn routing)."""
    # Keep `q` in the query string — values after `#map=` are ignored by OSM.
    q = urllib.parse.quote(name) if name else f"{lat:.6f},{lon:.6f}"
    return (
        f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}&q={q}"
        f"#map=17/{lat:.6f}/{lon:.6f}"
    )


def directions_link(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    mode: str = "walk",
) -> str:
    """OSM directions between two points with FOSSGIS OSRM profile."""
    engine = "fossgis_osrm_car" if mode == "car" else "fossgis_osrm_foot"
    if mode == "transit":
        engine = "fossgis_osrm_foot"
    return (
        "https://www.openstreetmap.org/directions?"
        f"engine={engine}&route={origin_lat:.6f}%2C{origin_lon:.6f}%3B{dest_lat:.6f}%2C{dest_lon:.6f}"
    )


def google_maps_link(lat: float, lon: float, name: str = "") -> str:
    label = urllib.parse.quote(name or f"{lat},{lon}")
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f}%2C{lon:.6f}+({label})"
