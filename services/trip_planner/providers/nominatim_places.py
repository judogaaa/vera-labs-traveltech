"""Nominatim PlacesProvider — verified OSM POIs when Overpass is unreachable."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .. import config
from ..models import LatLon, Place
from .base import PlacesProvider, ProviderError

# Short TTL cache — repeated named/category lookups within one plan() (and
# across sequential city E2E) should not re-hit Nominatim's 1 req/s budget.
_SEARCH_CACHE: dict[tuple, tuple[float, list[Place]]] = {}
_CACHE_TTL_S = 180.0
_CACHE_MAX = 256

CATEGORY_QUERIES: dict[str, list[str]] = {
    "attraction": ["attraction", "historic", "monument", "sightseeing"],
    "museum": ["museum"],
    "beach": ["beach"],
    "restaurant": ["restaurant"],
    "cafe": ["cafe"],
    "bar": ["bar", "pub"],
    "park": ["park"],
    "viewpoint": ["viewpoint"],
    "shopping": ["shop", "mall"],
    "religious": ["mosque", "place of worship", "church"],
}


class NominatimPlacesProvider(PlacesProvider):
    name = "nominatim"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
        self._last_call = 0.0
        self._cache: dict[str, Place] = {}

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < 1.05:
            time.sleep(1.05 - elapsed)
        self._last_call = time.monotonic()

    def search_places(
        self,
        query: str,
        near: LatLon,
        radius: int = 5000,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Place]:
        # Approximate viewbox from radius (deg ≈ m / 111000)
        d = max(radius, 1500) / 111_000
        viewbox = f"{near.lon - d},{near.lat + d},{near.lon + d},{near.lat - d}"
        terms = CATEGORY_QUERIES.get((category or "").lower(), [])
        q = (query or "").strip()
        # Prefer an explicit query (e.g. «Kul Sharif mosque») over bare category terms.
        if q and (not category or len(q.split()) >= 2 or category == "religious"):
            search_q = q
        elif category and terms:
            search_q = terms[0]
        elif q:
            search_q = q
        else:
            search_q = "attraction"
        named = bool(q) and not category
        cache_key = (
            "nominatim",
            search_q.lower(),
            round(near.lat, 3),
            round(near.lon, 3),
            category or "",
            int(radius // 2000),
            min(limit, 20),
        )
        hit = _SEARCH_CACHE.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_S:
            return list(hit[1])[:limit]
        params: dict[str, Any] = {
            "q": search_q,
            "format": "json",
            "limit": min(limit, 20),
            "addressdetails": 1,
            "extratags": 1,
        }
        # Named landmarks: prefer viewbox soft bias without hard bound so
        # «Dubai Marina» / «Kaleiçi» are not clipped to the wrong district.
        if named:
            params["viewbox"] = viewbox
            params["bounded"] = 0
            qlow = search_q.lower()
            if any(m in qlow for m in ("old town", "старый город", "historic centre", "historic center", "altstadt")):
                # Bias Nominatim toward settlements / named places, not POI tenants.
                params["featuretype"] = "settlement"
        else:
            params["viewbox"] = viewbox
            params["bounded"] = 1
        self._throttle()
        try:
            resp = self._client.get(f"{config.NOMINATIM_URL}/search", params=params)
            resp.raise_for_status()
            data: list[dict[str, Any]] = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("places_unavailable", f"Nominatim places failed: {exc}") from exc

        places: list[Place] = []
        for row in data:
            place = self._row_to_place(row, category)
            if not place:
                continue
            # If a specific category was requested, verify OSM tags support it.
            # The place.category may be set to the requested category as a fallback,
            # but we must verify the actual OSM tags.
            if category:
                cls = (row.get("class") or "").lower()
                typ = (row.get("type") or "").lower()
                osm_supports = False
                if category == "bar" and typ in {"bar", "pub", "biergarten"}:
                    osm_supports = True
                elif category == "restaurant" and typ in {"restaurant", "fast_food"}:
                    osm_supports = True
                elif category == "cafe" and typ == "cafe":
                    osm_supports = True
                elif category == "museum" and (typ == "museum" or cls == "museum"):
                    osm_supports = True
                elif category == "park" and typ == "park":
                    osm_supports = True
                elif category == "beach" and typ in {"beach", "beach_resort"}:
                    osm_supports = True
                elif category == "viewpoint" and typ == "viewpoint":
                    osm_supports = True
                elif category == "religious" and (
                    typ in {"place_of_worship", "mosque", "church", "cathedral", "temple", "synagogue"}
                    or cls in {"amenity", "religion", "building"}
                    and typ in {"mosque", "church", "cathedral", "temple", "place_of_worship"}
                ):
                    osm_supports = True
                elif category == "religious" and "mosque" in typ:
                    osm_supports = True
                elif category == "attraction" and cls == "tourism" and typ != "museum":
                    osm_supports = True
                elif category == "attraction" and cls == "historic" and typ != "museum":
                    osm_supports = True
                if not osm_supports:
                    # OSM tags don't support the requested category - skip this result
                    continue
            places.append(place)
            self._cache[place.placeId] = place
            if len(places) >= limit:
                break
        if len(_SEARCH_CACHE) >= _CACHE_MAX:
            _SEARCH_CACHE.clear()
        _SEARCH_CACHE[cache_key] = (time.monotonic(), list(places))
        return places

    def get_place_details(self, place_id: str) -> Place | None:
        if place_id in self._cache:
            return self._cache[place_id]
        if not place_id.startswith("osm:"):
            return None
        _, rest = place_id.split(":", 1)
        if "/" not in rest:
            return None
        osm_type, osm_id = rest.split("/", 1)
        prefix = {"node": "N", "way": "W", "relation": "R"}.get(osm_type)
        if not prefix:
            return None
        self._throttle()
        try:
            resp = self._client.get(
                f"{config.NOMINATIM_URL}/lookup",
                params={"osm_ids": f"{prefix}{osm_id}", "format": "json", "addressdetails": 1, "extratags": 1},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("places_unavailable", f"Nominatim lookup failed: {exc}") from exc
        if not data:
            return None
        place = self._row_to_place(data[0], None)
        if place:
            self._cache[place.placeId] = place
        return place

    def _row_to_place(self, row: dict[str, Any], category_hint: str | None) -> Place | None:
        name = row.get("name") or (row.get("display_name") or "").split(",")[0].strip()
        if not name:
            return None
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except (KeyError, TypeError, ValueError):
            return None
        osm_type = row.get("osm_type") or "node"
        osm_id = row.get("osm_id")
        if osm_id is None:
            return None
        place_id = f"osm:{osm_type}/{osm_id}"
        cls = (row.get("class") or "").lower()
        typ = (row.get("type") or "").lower()

        # Derive category from OSM tags; if ambiguous, prefer category_hint.
        derived: str | None = None
        if typ == "museum" or cls == "museum":
            derived = "museum"
        elif typ == "beach" or "beach" in typ:
            derived = "beach"
        elif typ in {"bar", "pub", "biergarten"} or (cls == "amenity" and typ in {"bar", "pub"}):
            derived = "bar"
        elif typ in {"restaurant", "fast_food"}:
            derived = "restaurant"
        elif typ == "cafe":
            derived = "cafe"
        elif typ == "park" or (cls == "leisure" and typ == "park"):
            derived = "park"
        elif typ == "viewpoint":
            derived = "viewpoint"
        elif cls == "shop":
            derived = "shopping"
        elif cls == "tourism" and typ == "attraction":
            derived = "attraction"
        elif cls == "historic" and typ != "museum":
            derived = "attraction"

        category = derived or category_hint or "attraction"
        place_kind = ""
        if cls == "place" and typ:
            place_kind = typ
        elif cls == "boundary":
            place_kind = "boundary"
        elif typ in {"suburb", "neighbourhood", "neighborhood", "quarter", "city_block"}:
            place_kind = typ
        elif typ == "museum" or cls == "museum":
            place_kind = "museum"
        elif cls in {"amenity", "tourism", "historic", "leisure"}:
            place_kind = typ or cls

        # If a specific category was requested but OSM tags don't support it,
        # the caller (search_places) will filter this out. We still create
        # the place with the derived/preferred category so the caller can decide.
        addr = row.get("display_name") or ""
        extratags = row.get("extratags") or {}
        photo = extratags.get("image") or extratags.get("wikimedia_commons")
        if isinstance(photo, str):
            photo = photo.strip() or None
            if photo and photo.lower().startswith("category:"):
                photo = None
        wd = extratags.get("wikidata")
        if isinstance(wd, str):
            wd = wd.strip().split(";", 1)[0].strip() or None
            if wd and not wd.upper().startswith("Q"):
                wd = None
        return Place(
            placeProvider=self.name,
            placeId=place_id,
            name=name,
            category=category,
            lat=lat,
            lon=lon,
            address=addr,
            description=f"{name} — OSM/{category}",
            photoUrl=photo,
            website=extratags.get("website") or extratags.get("contact:website"),
            openingHours=extratags.get("opening_hours"),
            wikidataId=wd,
            placeKind=place_kind,
        )


class FallbackPlacesProvider(PlacesProvider):
    """Try Overpass first; on failure use Nominatim (still verified OSM entities).

    For named queries (no category) merge both sources so a weak Overpass token
    hit cannot block Nominatim from finding the real landmark.
    """

    name = "overpass+nominatim"

    def __init__(self, primary: PlacesProvider, fallback: PlacesProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self._active = primary.name

    def search_places(
        self,
        query: str,
        near: LatLon,
        radius: int = 5000,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Place]:
        named = bool((query or "").strip()) and not category
        # Nominatim-first for named landmarks AND amenity categories.
        # Overpass-first on museum/restaurant/cafe burned 30–50s and left later
        # wishes as budget_timeout (Istanbul core-flows missing museum→dining).
        amenity_first = category in {
            "museum",
            "restaurant",
            "cafe",
            "bar",
            "viewpoint",
            "religious",
        }
        if named or amenity_first:
            try:
                nominatim_results = self.fallback.search_places(query, near, radius, category, limit)
            except ProviderError:
                nominatim_results = []
            if nominatim_results:
                self._active = self.fallback.name
                self.name = "overpass+nominatim"
                return nominatim_results
            try:
                overpass_results = self.primary.search_places(query, near, radius, category, limit)
            except ProviderError:
                overpass_results = []
            self._active = self.primary.name if overpass_results else self.fallback.name
            self.name = "overpass+nominatim"
            return overpass_results

        try:
            primary_results = self.primary.search_places(query, near, radius, category, limit)
        except ProviderError:
            primary_results = []
        if primary_results:
            self._active = self.primary.name
            self.name = f"{self.primary.name}+{self.fallback.name}"
            return primary_results
        try:
            fallback_results = self.fallback.search_places(query, near, radius, category, limit)
        except ProviderError:
            fallback_results = []
        self._active = self.fallback.name
        self.name = self.fallback.name
        return fallback_results

    def get_place_details(self, place_id: str) -> Place | None:
        for provider in (self.primary, self.fallback):
            try:
                place = provider.get_place_details(place_id)
                if place:
                    return place
            except ProviderError:
                continue
        return None
