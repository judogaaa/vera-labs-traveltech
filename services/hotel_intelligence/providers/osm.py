"""Overpass / Nominatim helpers with file cache.

On live failure + cache miss: return empty results with error status.
Never fabricates POIs.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .. import config

_DEFAULT_TIMEOUT = config.OSM_TIMEOUT_S

# Line/route name patterns that are not entrances/stations
_LINE_NAME_RE = re.compile(r"(?i)hatt[ıi]|metro hatt|line$")


def _cache_path(key: str) -> Path:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return config.CACHE_DIR / f"osm_{digest}.json"


def _read_cache(key: str) -> dict[str, Any] | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(key: str, payload: dict[str, Any]) -> None:
    path = _cache_path(key)
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")


def _empty(error: str) -> dict[str, Any]:
    return {
        "status": "error",
        "error": error,
        "items": [],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _overpass_query(ql: str, *, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    cache_key = f"overpass|{ql}"
    cached = _read_cache(cache_key)
    if cached is not None:
        out = dict(cached)
        out["status"] = "cache"
        return out

    last_err = "overpass_failed"
    for url in config.OVERPASS_MIRRORS or [config.OVERPASS_URL]:
        try:
            with httpx.Client(
                timeout=timeout, headers={"User-Agent": config.USER_AGENT}
            ) as client:
                resp = client.post(url, data={"data": ql})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            last_err = f"overpass_failed: {type(exc).__name__}: {exc}"
            continue

        elements = data.get("elements") or []
        items = [_normalize_element(el) for el in elements]
        items = [i for i in items if i is not None]
        payload = {
            "status": "ok",
            "error": None,
            "items": items,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_uri": url,
            "provider": "overpass",
        }
        _write_cache(cache_key, payload)
        return payload
    return _empty(last_err)


def _normalize_element(el: dict[str, Any]) -> dict[str, Any] | None:
    tags = el.get("tags") or {}
    lat = el.get("lat")
    lon = el.get("lon")
    used_center = False
    if lat is None or lon is None:
        center = el.get("center") or {}
        lat = center.get("lat")
        lon = center.get("lon")
        used_center = lat is not None and lon is not None
    if lat is None or lon is None:
        return None
    osm_type = el.get("type", "node")
    osm_id = el.get("id")
    return {
        "osm_type": osm_type,
        "osm_id": osm_id,
        "lat": float(lat),
        "lon": float(lon),
        "name": tags.get("name") or tags.get("name:en") or tags.get("name:ru"),
        "tags": tags,
        "used_way_center": used_center and osm_type in {"way", "relation"},
        "uri": f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if osm_id else "https://www.openstreetmap.org/",
    }


def nearby_pois(
    lat: float,
    lon: float,
    radius_m: int,
    tags: list[str],
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    prefer_local: bool | None = None,
) -> dict[str, Any]:
    """Query OSM for nodes/ways matching Overpass tag filters within radius.

    Prefers a local Istanbul snapshot when present (reproducible, no live Overpass).
    ``tags`` entries are Overpass selectors without surrounding brackets, e.g.
    ``'railway=station'`` or ``'amenity=pharmacy'``.
    """
    if not tags:
        return _empty("no_tags")
    use_local = (
        config.HOTEL_INTELLIGENCE_PREFER_LOCAL_OSM if prefer_local is None else prefer_local
    )
    if use_local:
        from .local_osm import query_local

        local = query_local(lat, lon, radius_m, tags)
        if local is not None:
            return local
    selectors = []
    for tag in tags:
        tag = tag.strip().strip("[]")
        selectors.append(f'node[{tag}](around:{int(radius_m)},{lat},{lon});')
        selectors.append(f'way[{tag}](around:{int(radius_m)},{lat},{lon});')
    ql = f"[out:json][timeout:{int(timeout)}];({''.join(selectors)});out center tags;"
    return _overpass_query(ql, timeout=timeout)


def _nominatim_search_nearby(
    lat: float,
    lon: float,
    query: str,
    *,
    radius_m: int = 2500,
    limit: int = 8,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Nominatim bounded search — used when Overpass SSL/mirrors fail."""
    dlat = radius_m / 111_000.0
    dlon = radius_m / (111_000.0 * max(0.2, abs(math.cos(math.radians(lat)))))
    viewbox = f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"
    cache_key = f"nominatim_search|{query}|{lat:.5f}|{lon:.5f}|{radius_m}"
    cached = _read_cache(cache_key)
    if cached is not None:
        out = dict(cached)
        out["status"] = "cache"
        return out
    url = f"{config.NOMINATIM_URL}/search"
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": config.USER_AGENT}) as client:
            resp = client.get(
                url,
                params={
                    "q": query,
                    "format": "json",
                    "limit": limit,
                    "bounded": 1,
                    "viewbox": viewbox,
                    "addressdetails": 0,
                },
            )
            resp.raise_for_status()
            rows = resp.json()
            time.sleep(1.0)  # Nominatim usage policy (≥1 req/s)
    except Exception as exc:  # noqa: BLE001
        return _empty(f"nominatim_search_failed: {type(exc).__name__}: {exc}")

    items: list[dict[str, Any]] = []
    for row in rows or []:
        try:
            items.append(
                {
                    "osm_type": row.get("osm_type") or "node",
                    "osm_id": row.get("osm_id"),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "name": row.get("display_name", "").split(",")[0].strip() or row.get("name"),
                    "tags": {
                        "nominatim_class": row.get("class"),
                        "nominatim_type": row.get("type"),
                    },
                    "uri": (
                        f"https://www.openstreetmap.org/{row.get('osm_type')}/{row.get('osm_id')}"
                        if row.get("osm_id")
                        else "https://www.openstreetmap.org/"
                    ),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    payload = {
        "status": "ok",
        "error": None,
        "items": items,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_uri": url,
        "provider": "nominatim",
    }
    _write_cache(cache_key, payload)
    return payload


def _has_entrance_or_station_type(item: dict[str, Any]) -> bool:
    """True only for concrete stop/entrance tags — not Nominatim 'subway' lines."""
    t = item.get("tags") or {}
    if t.get("railway") == "subway_entrance":
        return True
    if t.get("station") == "subway":
        return True
    if t.get("railway") == "station":
        return True
    if t.get("public_transport") == "station":
        return True
    ntype = (t.get("nominatim_type") or "").lower()
    # Nominatim type=subway on a way is usually the LINE, not a station.
    if ntype in {"station", "subway_entrance", "stop", "halt"}:
        return True
    if ntype == "subway" and (item.get("osm_type") or "").lower() == "node":
        return True
    return False


def _is_line_geometry(item: dict[str, Any]) -> bool:
    """Reject metro line/route geometries that are not entrances/stations."""
    t = item.get("tags") or {}
    name = (item.get("name") or "")
    osm_type = (item.get("osm_type") or "").lower()
    nclass = (t.get("nominatim_class") or "").lower()
    ntype = (t.get("nominatim_type") or "").lower()

    # Turkish/English line titles («… Metro Hattı») are never walk targets.
    if _LINE_NAME_RE.search(name):
        return True
    if nclass == "route":
        return True
    # Nominatim class=railway type=subway on way/relation ≈ route geometry.
    if osm_type in {"way", "relation"} and ntype in {"subway", "route", "railway", "light_rail"}:
        return True
    if ntype in {"route", "railway"} and osm_type in {"way", "relation"}:
        return True
    if t.get("route") == "subway" and osm_type in {"way", "relation"}:
        return True
    if t.get("type") == "route" and osm_type == "relation":
        return True
    if item.get("used_way_center") and not _has_entrance_or_station_type(item):
        return True
    # Refuse non-node geometries without explicit station/entrance OSM tags.
    if osm_type in {"way", "relation"} and not (
        t.get("railway") in {"station", "subway_entrance"}
        or t.get("station") == "subway"
        or t.get("public_transport") == "station"
    ):
        return True
    return False


def _access_point_kind(item: dict[str, Any]) -> str:
    t = item.get("tags") or {}
    osm_type = (item.get("osm_type") or "").lower()
    ntype = (t.get("nominatim_type") or "").lower()
    if t.get("railway") == "subway_entrance" or ntype == "subway_entrance":
        return "entrance"
    if osm_type == "node" and (
        t.get("railway") == "station"
        or t.get("station") == "subway"
        or ntype in {"station", "subway", "stop", "halt"}
    ):
        return "station_node"
    if osm_type == "node" and t.get("public_transport") == "station":
        return "station_node"
    if osm_type in {"way", "relation"} or item.get("used_way_center"):
        return "unconfirmed_station"
    if _has_entrance_or_station_type(item):
        return "station_node"
    return "unconfirmed_station"


def _priority(item: dict[str, Any]) -> tuple[int, float]:
    """Prefer subway_entrance (node) > station (node) > public_transport=station node."""
    kind = _access_point_kind(item)
    rank = {"entrance": 0, "station_node": 1, "unconfirmed_station": 2}.get(kind, 3)
    return (rank, 0.0)


def _is_metro_candidate(item: dict[str, Any]) -> bool:
    t = item.get("tags") or {}
    if t.get("station") == "subway":
        return True
    if t.get("railway") in {"subway", "subway_entrance"}:
        return True
    if t.get("railway") == "station" and t.get("subway") in {"yes", "true"}:
        return True
    name = (item.get("name") or "").lower()
    if "metro" in name or "m1" in name or "m2" in name or "m4" in name:
        return True
    ntype = (t.get("nominatim_type") or "").lower()
    nclass = (t.get("nominatim_class") or "").lower()
    if nclass in {"railway", "public_transport"} and ntype in {
        "station",
        "subway",
        "subway_entrance",
        "stop",
        "halt",
    }:
        return True
    if t.get("public_transport") == "station" and t.get("railway") == "station":
        return True
    return t.get("railway") == "station"


def nearest_metro(
    lat: float,
    lon: float,
    *,
    radius_m: int = 2500,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Find nearest metro / subway / light-rail stop. Empty on failure.

    Prefer entrance/station nodes; reject line/route geometries.
    Never invents a station.
    """
    result = nearby_pois(
        lat,
        lon,
        radius_m,
        tags=[
            "railway=station",
            "station=subway",
            "railway=subway_entrance",
            "public_transport=station",
        ],
        timeout=timeout,
    )
    overpass_error = result.get("status") == "error"

    items = list(result.get("items") or [])
    if overpass_error or not items:
        # Prefer entrance/station wording — avoid «metro hattı» line hits.
        for q in (
            "subway entrance",
            "metro girişi",
            "metro station",
            "subway station",
        ):
            nom = _nominatim_search_nearby(lat, lon, q, radius_m=radius_m, timeout=timeout)
            if nom.get("status") == "error" or not nom.get("items"):
                continue
            # Keep merging until we have a non-line node candidate.
            batch = list(nom.get("items") or [])
            if result.get("status") == "error" or not items:
                result = nom
                items = batch
            else:
                items.extend(batch)
            tentative = [
                i
                for i in items
                if not _is_line_geometry(i)
                and (i.get("osm_type") or "").lower() == "node"
            ]
            if tentative:
                break
        if not items and overpass_error:
            return result

    rejected = 0
    accepted: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for item in items:
        key = (item.get("osm_type"), item.get("osm_id"))
        if key in seen and key != (None, None):
            continue
        seen.add(key)
        if _is_line_geometry(item):
            rejected += 1
            continue
        if _is_metro_candidate(item) or _has_entrance_or_station_type(item):
            accepted.append(item)

    # Prefer nodes with entrance/station — never fall back to rejected lines.
    entrances = [
        i
        for i in accepted
        if _access_point_kind(i) == "entrance" and (i.get("osm_type") or "").lower() == "node"
    ]
    station_nodes = [
        i
        for i in accepted
        if _access_point_kind(i) == "station_node" and (i.get("osm_type") or "").lower() == "node"
    ]
    # Unconfirmed only if it is still a node with station-like tags (not a line).
    unconfirmed = [
        i
        for i in accepted
        if _access_point_kind(i) == "unconfirmed_station"
        and (i.get("osm_type") or "").lower() == "node"
    ]

    pool = entrances or station_nodes or unconfirmed
    if not pool:
        return {
            "status": result.get("status", "ok"),
            "error": None,
            "item": None,
            "items": [],
            "rejected_line_candidates": rejected,
            "access_point_kind": "none",
            "fetched_at": result.get("fetched_at"),
            "source_uri": result.get("source_uri"),
            "provider": result.get("provider"),
        }

    def _dist2(item: dict[str, Any]) -> float:
        return (float(item["lat"]) - lat) ** 2 + (float(item["lon"]) - lon) ** 2

    best = min(pool, key=lambda i: (_priority(i)[0], _dist2(i)))
    kind = _access_point_kind(best)
    return {
        "status": result.get("status", "ok"),
        "error": None,
        "item": best,
        "items": pool,
        "rejected_line_candidates": rejected,
        "access_point_kind": kind,
        "fetched_at": result.get("fetched_at"),
        "source_uri": result.get("source_uri"),
        "provider": result.get("provider"),
    }


def roads_nearby(
    lat: float,
    lon: float,
    *,
    radius_m: int = 200,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Highways / rail / nightlife amenities for noise proxy. Never claims dB."""
    tags = [
        "highway=motorway",
        "highway=trunk",
        "highway=primary",
        "highway=secondary",
        "railway=rail",
        "amenity=bar",
        "amenity=nightclub",
        "amenity=pub",
    ]
    return nearby_pois(lat, lon, radius_m, tags, timeout=timeout)


def nominatim_reverse(
    lat: float,
    lon: float,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    cache_key = f"nominatim|{lat:.6f}|{lon:.6f}"
    cached = _read_cache(cache_key)
    if cached is not None:
        out = dict(cached)
        out["status"] = "cache"
        return out
    url = f"{config.NOMINATIM_URL}/reverse"
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": config.USER_AGENT}) as client:
            resp = client.get(
                url,
                params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return _empty(f"nominatim_failed: {type(exc).__name__}: {exc}")
    payload = {
        "status": "ok",
        "error": None,
        "items": [data],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_uri": url,
    }
    _write_cache(cache_key, payload)
    time.sleep(0.05)
    return payload
