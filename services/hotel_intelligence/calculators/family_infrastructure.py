"""Nearby playgrounds and parks from OSM."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..models import AttributeObservation
from ..providers.osm import nearby_pois
from ._common import make_estimated, make_unknown, source

METHOD = "osm_family_infra"
METHOD_VERSION = "v1"
ATTRIBUTE_KEY = "family_infrastructure"

_TAGS = [
    "leisure=playground",
    "leisure=park",
    "leisure=garden",
]


def compute_family_infrastructure(
    hotel_id: str,
    lat: float,
    lon: float,
    *,
    radius_m: int = 800,
    pois_fn: Callable[..., dict[str, Any]] | None = None,
) -> AttributeObservation:
    fn = pois_fn or nearby_pois
    res = fn(lat, lon, radius_m, _TAGS)
    if res.get("status") == "error":
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason=res.get("error") or "osm_unavailable",
            calculation_inputs={"lat": lat, "lon": lon, "radius_m": radius_m},
        )

    playgrounds = []
    parks = []
    for item in res.get("items") or []:
        tags = item.get("tags") or {}
        entry = {
            "name": item.get("name"),
            "uri": item.get("uri"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
        }
        if tags.get("leisure") == "playground":
            playgrounds.append(entry)
        elif tags.get("leisure") in {"park", "garden"}:
            parks.append(entry)

    if not playgrounds and not parks:
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason="no_family_pois",
            calculation_inputs={"lat": lat, "lon": lon, "radius_m": radius_m},
        )

    fetched = res.get("fetched_at")
    try:
        fetched_at = (
            datetime.fromisoformat(str(fetched).replace("Z", "+00:00"))
            if fetched
            else datetime.now(timezone.utc)
        )
    except ValueError:
        fetched_at = datetime.now(timezone.utc)

    src = source(
        "osm",
        res.get("source_uri") or "https://www.openstreetmap.org/",
        fetched_at=fetched_at,
    )
    value = {
        "playground_count": len(playgrounds),
        "park_count": len(parks),
        "playgrounds": playgrounds[:15],
        "parks": parks[:15],
        "note": (
            "Proximity of a playground/park does not imply a safe walk, "
            "crossing quality, or hotel family policies."
        ),
    }
    return make_estimated(
        hotel_id=hotel_id,
        attribute_key=ATTRIBUTE_KEY,
        value=value,
        unit=None,
        sources=[src],
        confidence=0.6,
        method=METHOD,
        method_version=METHOD_VERSION,
        calculation_inputs={"lat": lat, "lon": lon, "radius_m": radius_m},
    )
