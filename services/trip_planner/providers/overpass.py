from __future__ import annotations

import re
import time
from typing import Any

import httpx

from .. import config
from ..models import LatLon, Place
from .base import PlacesProvider, ProviderError

_SEARCH_CACHE: dict[tuple, tuple[float, list[Place]]] = {}
_CACHE_TTL_S = 180.0
_CACHE_MAX = 256

CATEGORY_TAGS: dict[str, list[str]] = {
    "attraction": [
        'node["tourism"="attraction"]',
        'node["historic"]',
        'node["tourism"="museum"]',
        'way["tourism"="attraction"]',
        'way["tourism"="museum"]',
        'way["historic"]',
    ],
    "museum": ['node["tourism"="museum"]', 'way["tourism"="museum"]'],
    "beach": ['node["natural"="beach"]', 'way["natural"="beach"]', 'node["leisure"="beach_resort"]'],
    "restaurant": ['node["amenity"="restaurant"]', 'node["amenity"="cafe"]'],
    "cafe": ['node["amenity"="cafe"]', 'node["amenity"="bar"]'],
    "bar": ['node["amenity"="bar"]', 'node["amenity"="pub"]', 'node["amenity"="cafe"]'],
    "park": ['node["leisure"="park"]', 'way["leisure"="park"]'],
    "viewpoint": [
        'node["tourism"="viewpoint"]',
        'way["tourism"="viewpoint"]',
        'node["tourism"="attraction"]["viewpoint"]',
        'node["man_made"="tower"]["tourism"]',
        'node["man_made"="tower"]["building"="yes"]',
    ],
    "shop": ['node["shop"]'],
    "shopping": ['node["shop"]'],
    "cafe": ['node["amenity"="cafe"]'],
    "religious": ['node["amenity"="place_of_worship"]', 'way["amenity"="place_of_worship"]'],
}

DEFAULT_TAGS = (
    CATEGORY_TAGS["attraction"]
    + CATEGORY_TAGS["museum"]
    + CATEGORY_TAGS["park"]
    + CATEGORY_TAGS["viewpoint"]
    + CATEGORY_TAGS["beach"]
    + CATEGORY_TAGS["religious"]
    + CATEGORY_TAGS["restaurant"][:1]
    + [
        'way["highway"="pedestrian"]',
        'way["highway"="footway"]["name"]',
        'node["tourism"="yes"]',
        'relation["type"="multipolygon"]["historic"="castle"]',
        'way["historic"="castle"]',
        'node["tourism"="attraction"]',
        'way["place"="neighbourhood"]',
        'node["place"="neighbourhood"]',
        'way["place"="suburb"]',
    ]
)

# Public mirrors — primary from ENV, then fallbacks on 429/5xx/SSL
OVERPASS_MIRRORS = [
    config.OVERPASS_URL,
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]


def _category_from_tags(tags: dict[str, str]) -> str:
    if tags.get("tourism") == "museum" or tags.get("amenity") == "museum":
        return "museum"
    if tags.get("natural") == "beach" or tags.get("leisure") == "beach_resort":
        return "beach"
    if tags.get("amenity") in {"restaurant", "cafe", "fast_food", "bar", "pub"}:
        if tags.get("amenity") in {"bar", "pub"}:
            return "bar"
        return "restaurant" if tags.get("amenity") != "cafe" else "cafe"
    if tags.get("leisure") == "park":
        return "park"
    if tags.get("tourism") == "viewpoint" or tags.get("viewpoint"):
        return "viewpoint"
    if tags.get("man_made") == "tower" and tags.get("tourism"):
        return "viewpoint"
    if tags.get("shop"):
        return "shopping"
    if tags.get("amenity") == "place_of_worship" or tags.get("building") in {
        "temple",
        "church",
        "cathedral",
        "mosque",
    }:
        return "religious"
    if tags.get("historic"):
        return "attraction"
    if tags.get("tourism"):
        return tags["tourism"]
    return "attraction"


class OverpassPlacesProvider(PlacesProvider):
    name = "overpass"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
        self._cache: dict[str, Place] = {}
        self._mirrors = list(dict.fromkeys([u for u in OVERPASS_MIRRORS if u]))

    def _post_ql(self, ql: str) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(2):
            url = self._mirrors[attempt % len(self._mirrors)]
            try:
                resp = self._client.post(url, data={"data": ql})
                if resp.status_code in {429, 502, 503, 504}:
                    last_err = ProviderError(
                        "places_unavailable",
                        f"Overpass HTTP {resp.status_code} from {url}",
                    )
                    time.sleep(1.0)
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                time.sleep(0.8)
        raise ProviderError("places_unavailable", f"Overpass search failed: {last_err}") from last_err

    def search_places(
        self,
        query: str,
        near: LatLon,
        radius: int = 5000,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Place]:
        q_lower = (query or "").strip().lower()
        named = bool(q_lower) and not category
        cache_key = (
            "overpass",
            q_lower,
            round(near.lat, 3),
            round(near.lon, 3),
            (category or "").lower(),
            int(radius // 2000),
            min(limit, 20),
        )
        hit = _SEARCH_CACHE.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_S:
            return list(hit[1])[:limit]
        around = f"(around:{int(radius)},{near.lat},{near.lon})"
        if named:
            # Targeted name search — avoid dumping every nearby POI (was 20–40s).
            tokens = [tok for tok in q_lower.replace(",", " ").split() if len(tok) > 2][:4]
            safe = [re.escape(t) for t in tokens]
            if not safe:
                return []
            # Multi-token: loose AND; single token: substring (scored later).
            pattern = ".*".join(safe) if len(safe) >= 2 else safe[0]
            name_keys = ("name", "name:en", "name:ru", "name:tr", "name:ar", "alt_name", "official_name")
            clauses = "\n".join(
                f'  nwr["{k}"~"{pattern}",i]{around};' for k in name_keys
            )
            # Prefer administrative / named areas for old towns & districts.
            place_clause = (
                f'  nwr["place"~"suburb|neighbourhood|quarter|city_block"]["name"~"{pattern}",i]{around};'
            )
            ql = f"""
            [out:json][timeout:10];
            (
            {place_clause}
            {clauses}
            );
            out center tags {max(limit * 2, 16)};
            """
        else:
            tags = CATEGORY_TAGS.get((category or "").lower(), DEFAULT_TAGS)
            # Cap tag fan-out for category dumps — fewer clauses → faster Overpass.
            if category and category.lower() in CATEGORY_TAGS:
                tags = CATEGORY_TAGS[category.lower()]
            else:
                tags = tags[:12]
            clauses = "\n".join(f"  {t}{around};" for t in tags)
            ql = f"""
            [out:json][timeout:12];
            (
            {clauses}
            );
            out center tags {max(limit * 2, 20)};
            """
        payload = self._post_ql(ql)

        places: list[Place] = []
        for el in payload.get("elements") or []:
            place = self._element_to_place(el)
            if not place:
                continue
            # If a specific category was requested, verify OSM tags support it.
            if category:
                tags = el.get("tags") or {}
                osm_supports = False
                if category == "bar" and tags.get("amenity") in {"bar", "pub", "biergarten"}:
                    osm_supports = True
                elif category == "restaurant" and tags.get("amenity") in {"restaurant", "fast_food"}:
                    osm_supports = True
                elif category == "cafe" and tags.get("amenity") == "cafe":
                    osm_supports = True
                elif category == "museum" and tags.get("tourism") == "museum":
                    osm_supports = True
                elif category == "park" and tags.get("leisure") == "park":
                    osm_supports = True
                elif category == "beach" and tags.get("natural") == "beach":
                    osm_supports = True
                elif category == "shopping" and tags.get("shop"):
                    osm_supports = True
                elif category == "religious" and (
                    tags.get("amenity") == "place_of_worship" or tags.get("building") == "temple"
                ):
                    osm_supports = True
                elif category == "viewpoint" and (
                    tags.get("tourism") == "viewpoint"
                    or tags.get("viewpoint")
                    or (tags.get("man_made") == "tower" and tags.get("tourism"))
                ):
                    osm_supports = True
                elif category == "attraction" and tags.get("tourism") in {
                    "attraction",
                    "viewpoint",
                    "artwork",
                    "gallery",
                }:
                    osm_supports = True
                elif category == "attraction" and "historic" in tags and tags.get("tourism") != "museum":
                    osm_supports = True
                if not osm_supports:
                    continue
            # Multilingual OSM name fields for token match (not display name alone).
            tags = el.get("tags") or {}
            name_blob = " ".join(
                str(tags.get(k) or "")
                for k in (
                    "name",
                    "name:en",
                    "name:ru",
                    "name:tr",
                    "name:ar",
                    "alt_name",
                    "official_name",
                    "int_name",
                )
            ).lower()
            if q_lower and not category:
                tokens = [tok for tok in q_lower.split() if len(tok) > 2]
                # Require ALL significant tokens for multi-word named queries
                # so «голубая мечеть» does not match every mosque.
                if len(tokens) >= 2:
                    if not all(tok in name_blob or tok in place.name.lower() for tok in tokens):
                        continue
                elif tokens and not any(
                    tok in name_blob or tok in place.name.lower() for tok in tokens
                ):
                    continue
            places.append(place)
            self._cache[place.placeId] = place
            if len(places) >= limit:
                break

        # Never dump arbitrary nearby POIs for a named query — empty means miss.
        if len(_SEARCH_CACHE) >= _CACHE_MAX:
            _SEARCH_CACHE.clear()
        _SEARCH_CACHE[cache_key] = (time.monotonic(), list(places))
        return places

    def search_by_wikidata(
        self,
        wikidata_id: str,
        near: LatLon,
        radius: int = 40_000,
        limit: int = 5,
    ) -> list[Place]:
        """Resolve a place by Wikidata Q-id near coordinates (districts/landmarks)."""
        qid = (wikidata_id or "").strip()
        if not qid.upper().startswith("Q"):
            return []
        cache_key = ("overpass_wd", qid.upper(), round(near.lat, 2), round(near.lon, 2), int(radius // 5000))
        hit = _SEARCH_CACHE.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_S:
            return list(hit[1])[:limit]
        around = f"(around:{int(radius)},{near.lat},{near.lon})"
        ql = f"""
        [out:json][timeout:12];
        (
          nwr["wikidata"="{qid}"]{around};
        );
        out center tags {max(limit, 3)};
        """
        try:
            payload = self._post_ql(ql)
        except ProviderError:
            return []
        places: list[Place] = []
        for el in payload.get("elements") or []:
            place = self._element_to_place(el)
            if not place:
                continue
            places.append(place)
            self._cache[place.placeId] = place
            if len(places) >= limit:
                break
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
        ql = f"""
        [out:json][timeout:15];
        {osm_type}({osm_id});
        out center tags;
        """
        try:
            elements = (self._post_ql(ql) or {}).get("elements") or []
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("places_unavailable", f"Overpass details failed: {exc}") from exc
        if not elements:
            return None
        place = self._element_to_place(elements[0])
        if place:
            self._cache[place.placeId] = place
        return place

    def _element_to_place(self, el: dict[str, Any]) -> Place | None:
        tags = el.get("tags") or {}
        name = tags.get("name:ru") or tags.get("name:en") or tags.get("name")
        if not name:
            return None
        if "lat" in el and "lon" in el:
            lat, lon = float(el["lat"]), float(el["lon"])
        else:
            c = el.get("center") or {}
            if "lat" not in c or "lon" not in c:
                return None
            lat, lon = float(c["lat"]), float(c["lon"])
        osm_type = el.get("type", "node")
        osm_id = el.get("id")
        place_id = f"osm:{osm_type}/{osm_id}"
        address_parts = [
            tags.get("addr:street"),
            tags.get("addr:housenumber"),
            tags.get("addr:city"),
        ]
        address = ", ".join(p for p in address_parts if p) or tags.get("addr:full") or ""
        desc = tags.get("description") or tags.get("description:ru") or tags.get("wikipedia") or ""
        if desc.startswith("wikipedia"):
            desc = f"POI из OpenStreetMap ({_category_from_tags(tags)})"
        # Keep File: / Wikidata refs — resolved later by photos.enrich_* (not dropped).
        photo = tags.get("image") or tags.get("wikimedia_commons") or None
        if isinstance(photo, str):
            photo = photo.strip() or None
            if photo and photo.lower().startswith("category:"):
                photo = None
        wd = tags.get("wikidata")
        if isinstance(wd, str):
            wd = wd.strip().split(";", 1)[0].strip() or None
            if wd and not wd.upper().startswith("Q"):
                wd = None
        rating = None
        if tags.get("stars"):
            try:
                rating = float(str(tags["stars"]).replace("*", "").strip())
            except ValueError:
                rating = None
        place_kind = (
            tags.get("place")
            or ("museum" if tags.get("tourism") == "museum" else "")
            or tags.get("tourism")
            or tags.get("amenity")
            or tags.get("historic")
            or ("boundary" if tags.get("boundary") else "")
            or ""
        )
        return Place(
            placeProvider=self.name,
            placeId=place_id,
            name=name,
            category=_category_from_tags(tags),
            lat=lat,
            lon=lon,
            address=address,
            description=desc or f"{name} — {_category_from_tags(tags)}",
            photoUrl=photo,
            rating=rating,
            website=tags.get("website") or tags.get("contact:website"),
            openingHours=tags.get("opening_hours"),
            wikidataId=wd,
            placeKind=str(place_kind or ""),
        )
