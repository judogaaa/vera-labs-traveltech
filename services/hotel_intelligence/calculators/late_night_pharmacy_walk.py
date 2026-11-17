"""Walk minutes to a late-night / 24h pharmacy (hours-confirmed only)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..models import AttributeObservation
from ..providers.osm import nearby_pois
from ..providers.walking import WalkingProvider
from ._common import make_estimated, make_unknown, source
from .night_services import _suggests_late_or_24h

METHOD = "late_night_pharmacy_walk_calc"
METHOD_VERSION = "v1"
ATTRIBUTE_KEY = "late_night_pharmacy_walk"


def compute_late_night_pharmacy_walk(
    hotel_id: str,
    lat: float,
    lon: float,
    *,
    radius_m: int = 900,
    pois_fn: Callable[..., dict[str, Any]] | None = None,
    walking: WalkingProvider | None = None,
) -> AttributeObservation:
    fn = pois_fn or nearby_pois
    walker = walking or WalkingProvider()
    res = fn(lat, lon, radius_m, ["amenity=pharmacy"])
    if res.get("status") == "error":
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason=res.get("error") or "osm_unavailable",
            calculation_inputs={"lat": lat, "lon": lon, "radius_m": radius_m},
        )

    candidates = []
    for item in res.get("items") or []:
        tags = item.get("tags") or {}
        kind = _suggests_late_or_24h(tags.get("opening_hours") or "")
        if kind:
            candidates.append((item, kind))

    fetched_at = _parse_fetched(res.get("fetched_at"))
    if not candidates:
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason="no_pharmacy_with_late_or_24h_opening_hours",
            sources=[
                source(
                    "osm",
                    res.get("source_uri") or "https://www.openstreetmap.org/",
                    fetched_at=fetched_at,
                )
            ],
            calculation_inputs={
                "lat": lat,
                "lon": lon,
                "radius_m": radius_m,
                "nearby_pharmacy_count": len(res.get("items") or []),
            },
        )

    def _dist2(item: dict[str, Any]) -> float:
        return (float(item["lat"]) - lat) ** 2 + (float(item["lon"]) - lon) ** 2

    best_item, kind = min(candidates, key=lambda pair: _dist2(pair[0]))
    route = walker.route((lat, lon), (float(best_item["lat"]), float(best_item["lon"])))
    osm_src = source(
        "osm",
        best_item.get("uri") or res.get("source_uri") or "https://www.openstreetmap.org/",
        fetched_at=fetched_at,
    )
    if route is None:
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason="routing_failed",
            sources=[osm_src],
            calculation_inputs={"lat": lat, "lon": lon, "pharmacy": best_item.get("name")},
        )

    osrm_src = source(
        "osrm",
        "https://routing.openstreetmap.de/routed-foot",
        fetched_at=datetime.now(timezone.utc),
    )
    value = {
        "distance_m": route.distance_m,
        "duration_min": round(route.duration_s / 60.0, 1),
        "confirmed_24h": kind == "24h",
        "late_or_24h": True,
        "pharmacy_name": best_item.get("name"),
        "opening_hours": (best_item.get("tags") or {}).get("opening_hours"),
    }
    return make_estimated(
        hotel_id=hotel_id,
        attribute_key=ATTRIBUTE_KEY,
        value=value,
        unit="min",
        sources=[osm_src, osrm_src],
        confidence=0.6,
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
