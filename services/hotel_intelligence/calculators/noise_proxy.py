"""Heuristic external noise risk from nearby road/rail/nightlife OSM features.

Values: low | medium | elevated | insufficient_data.
Never claims measured dB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..models import AttributeObservation
from ..providers.osm import roads_nearby
from ._common import make_estimated, make_unknown, source

METHOD = "osm_noise_proxy"
METHOD_VERSION = "v1"
ATTRIBUTE_KEY = "external_noise_risk"


def _classify(counts: dict[str, int]) -> str:
    score = (
        counts.get("highway_motorway", 0) * 4
        + counts.get("highway_trunk", 0) * 3
        + counts.get("highway_primary", 0) * 2
        + counts.get("highway_secondary", 0) * 1
        + counts.get("railway_rail", 0) * 3
        + counts.get("amenity_bar", 0) * 1
        + counts.get("amenity_nightclub", 0) * 2
        + counts.get("amenity_pub", 0) * 1
    )
    if score >= 8:
        return "elevated"
    if score >= 3:
        return "medium"
    return "low"


def _count_tags(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        tags = item.get("tags") or {}
        hw = tags.get("highway")
        if hw in {"motorway", "trunk", "primary", "secondary"}:
            key = f"highway_{hw}"
            counts[key] = counts.get(key, 0) + 1
        if tags.get("railway") == "rail":
            counts["railway_rail"] = counts.get("railway_rail", 0) + 1
        am = tags.get("amenity")
        if am in {"bar", "nightclub", "pub"}:
            key = f"amenity_{am}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def _has_road_or_rail(counts: dict[str, int]) -> bool:
    return any(
        counts.get(k, 0) > 0
        for k in (
            "highway_motorway",
            "highway_trunk",
            "highway_primary",
            "highway_secondary",
            "railway_rail",
        )
    )


def compute_noise_risk(
    hotel_id: str,
    lat: float,
    lon: float,
    *,
    radius_m: int = 200,
    roads_fn: Callable[..., dict[str, Any]] | None = None,
) -> AttributeObservation:
    fn = roads_fn or roads_nearby
    res = fn(lat, lon, radius_m=radius_m)
    if res.get("status") == "error":
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason=res.get("error") or "osm_unavailable",
            calculation_inputs={"lat": lat, "lon": lon, "radius_m": radius_m},
        )

    items = list(res.get("items") or [])
    if not items:
        # Honest: no OSM features found in radius → insufficient data, not "quiet"
        value = {
            "risk": "insufficient_data",
            "note": "No highway/rail/nightlife features returned; not a silence guarantee.",
            "counts": {},
            "unit_note": "heuristic risk bucket — not measured dB",
        }
        src = source(
            "osm",
            res.get("source_uri") or "https://www.openstreetmap.org/",
            fetched_at=_parse_fetched(res.get("fetched_at")),
        )
        return make_estimated(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            value=value,
            unit=None,
            sources=[src],
            confidence=0.35,
            method=METHOD,
            method_version=METHOD_VERSION,
            calculation_inputs={"lat": lat, "lon": lon, "radius_m": radius_m, "item_count": 0},
        )

    counts = _count_tags(items)
    provider = (res.get("provider") or "").lower()
    src = source(
        "osm",
        res.get("source_uri") or items[0].get("uri") or "https://www.openstreetmap.org/",
        fetched_at=_parse_fetched(res.get("fetched_at")),
    )
    nightlife = (
        counts.get("amenity_bar", 0)
        + counts.get("amenity_nightclub", 0)
        + counts.get("amenity_pub", 0)
    )
    has_transport = _has_road_or_rail(counts)
    # Never claim "low" without road/rail evidence. Nightlife alone may raise risk.
    if not has_transport:
        if nightlife >= 3 or counts.get("amenity_nightclub", 0) >= 1:
            risk = "elevated" if nightlife >= 4 or counts.get("amenity_nightclub", 0) else "medium"
            value = {
                "risk": risk,
                "counts": counts,
                "feature_count": len(items),
                "note": (
                    "Risk from nightlife OSM amenities only; road/rail sample incomplete. "
                    "Not measured dB; not a silence guarantee."
                ),
                "unit_note": "heuristic risk bucket — not measured dB",
            }
            return make_estimated(
                hotel_id=hotel_id,
                attribute_key=ATTRIBUTE_KEY,
                value=value,
                unit=None,
                sources=[src],
                confidence=0.45,
                method=METHOD,
                method_version=METHOD_VERSION,
                calculation_inputs={
                    "lat": lat,
                    "lon": lon,
                    "radius_m": radius_m,
                    "provider": provider or "unknown",
                },
            )
        value = {
            "risk": "insufficient_data",
            "counts": counts,
            "feature_count": len(items),
            "note": (
                "Insufficient road/rail evidence for quietness; "
                "empty or sparse amenity sample is not a low-noise claim."
            ),
            "unit_note": "heuristic risk bucket — not measured dB",
        }
        return make_estimated(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            value=value,
            unit=None,
            sources=[src],
            confidence=0.35,
            method=METHOD,
            method_version=METHOD_VERSION,
            calculation_inputs={
                "lat": lat,
                "lon": lon,
                "radius_m": radius_m,
                "provider": provider or "unknown",
            },
        )

    risk = _classify(counts)
    value = {
        "risk": risk,
        "counts": counts,
        "feature_count": len(items),
        "unit_note": "heuristic risk bucket — not measured dB",
    }
    conf = 0.55 if risk != "insufficient_data" else 0.35
    return make_estimated(
        hotel_id=hotel_id,
        attribute_key=ATTRIBUTE_KEY,
        value=value,
        unit=None,
        sources=[src],
        confidence=conf,
        method=METHOD,
        method_version=METHOD_VERSION,
        calculation_inputs={"lat": lat, "lon": lon, "radius_m": radius_m},
    )


def _parse_fetched(fetched: Any) -> datetime:
    if isinstance(fetched, str):
        try:
            return datetime.fromisoformat(fetched.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
