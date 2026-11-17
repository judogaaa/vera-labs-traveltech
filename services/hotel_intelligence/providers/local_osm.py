"""Local OSM POI index for reproducible enrich without live Overpass.

Snapshot format (istanbul_pois.json):
{
  "attribution": "© OpenStreetMap contributors (ODbL)",
  "fetched_at": "...",
  "bbox": [south, west, north, east],
  "source": "overpass|assembled_cache",
  "items": [ {osm_type, osm_id, lat, lon, name, tags, uri}, ... ]
}
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from .. import config


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


@lru_cache(maxsize=4)
def load_index(path: str | None = None) -> dict[str, Any] | None:
    p = Path(path) if path else config.OSM_LOCAL_INDEX
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return None
    return data


def clear_index_cache() -> None:
    load_index.cache_clear()


def _tag_matches(item_tags: dict[str, Any], selector: str) -> bool:
    """Match Overpass-style ``key=value`` or ``key~regex`` selectors."""
    sel = selector.strip().strip("[]")
    if "~" in sel:
        key, _, pattern = sel.partition("~")
        key = key.strip().strip('"')
        pattern = pattern.strip().strip('"')
        val = str(item_tags.get(key) or "")
        import re

        return bool(re.search(pattern, val))
    if "=" in sel:
        key, _, value = sel.partition("=")
        return str(item_tags.get(key.strip())) == value.strip()
    return sel in item_tags


def query_local(
    lat: float,
    lon: float,
    radius_m: int,
    tags: list[str],
    *,
    index_path: str | None = None,
) -> dict[str, Any] | None:
    """Return nearby items from local snapshot, or None if snapshot missing."""
    idx = load_index(index_path)
    if idx is None:
        return None
    items_out: list[dict[str, Any]] = []
    for item in idx.get("items") or []:
        try:
            ilat = float(item["lat"])
            ilon = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if _haversine_m(lat, lon, ilat, ilon) > radius_m:
            continue
        itags = item.get("tags") or {}
        if tags and not any(_tag_matches(itags, t) for t in tags):
            continue
        items_out.append(item)
    return {
        "status": "ok",
        "error": None,
        "items": items_out,
        "fetched_at": idx.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
        "source_uri": idx.get("source_uri") or str(config.OSM_LOCAL_INDEX),
        "provider": "local_osm_snapshot",
        "attribution": idx.get("attribution") or "© OpenStreetMap contributors (ODbL)",
        "limitations": idx.get("limitations")
        or "Local snapshot; may lag live OSM; not a complete planet extract.",
    }
