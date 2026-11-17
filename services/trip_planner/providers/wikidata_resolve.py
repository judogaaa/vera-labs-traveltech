"""Resolve a Wikidata Q-id to a Place via P625 coordinates (universal fallback)."""
from __future__ import annotations

import time
from typing import Any

import httpx

from .. import config
from ..models import Place

_CACHE: dict[str, tuple[float, Place | None]] = {}
_TTL_S = 600.0


def place_from_wikidata(qid: str, *, fallback_name: str = "") -> Place | None:
    """Return a Place pinned by Wikidata coordinates, or None if unavailable."""
    key = (qid or "").strip().upper()
    if not key.startswith("Q"):
        return None
    hit = _CACHE.get(key)
    if hit and (time.monotonic() - hit[0]) < _TTL_S:
        return hit[1]
    place: Place | None = None
    try:
        with httpx.Client(timeout=12.0, headers={"User-Agent": config.USER_AGENT}) as client:
            resp = client.get(f"https://www.wikidata.org/wiki/Special:EntityData/{key}.json")
            resp.raise_for_status()
            ent = (resp.json().get("entities") or {}).get(key) or {}
        labels = ent.get("labels") or {}
        name = (
            (labels.get("ru") or {}).get("value")
            or (labels.get("en") or {}).get("value")
            or (labels.get("tr") or {}).get("value")
            or fallback_name
            or key
        )
        claims = ent.get("claims") or {}
        coords = _extract_p625(claims)
        if coords is None:
            _CACHE[key] = (time.monotonic(), None)
            return None
        lat, lon = coords
        place = Place(
            placeProvider="wikidata",
            placeId=f"wikidata:{key}",
            name=name,
            category="attraction",
            lat=lat,
            lon=lon,
            description=f"{name} — Wikidata/{key}",
            wikidataId=key,
            placeKind="suburb",
        )
    except Exception:  # noqa: BLE001
        place = None
    _CACHE[key] = (time.monotonic(), place)
    return place


def _extract_p625(claims: dict[str, Any]) -> tuple[float, float] | None:
    for snak in claims.get("P625") or []:
        val = ((snak.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        try:
            return float(val["latitude"]), float(val["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
    return None
