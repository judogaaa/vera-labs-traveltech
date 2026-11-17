"""Parking and pedestrian-zone hints from OSM near the hotel."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..models import AttributeObservation
from ..providers.osm import nearby_pois
from ._common import make_estimated, make_unknown, source

METHOD = "osm_car_access"
METHOD_VERSION = "v1"
ATTRIBUTE_KEY = "car_access"

_TAGS = [
    "amenity=parking",
    "amenity=parking_entrance",
    "highway=pedestrian",
    "highway=living_street",
]


def compute_car_access(
    hotel_id: str,
    lat: float,
    lon: float,
    *,
    radius_m: int = 250,
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

    parking = []
    pedestrian = []
    for item in res.get("items") or []:
        tags = item.get("tags") or {}
        entry = {
            "name": item.get("name"),
            "uri": item.get("uri"),
            "tags": {k: tags[k] for k in ("amenity", "highway", "access", "fee") if k in tags},
        }
        if tags.get("amenity") in {"parking", "parking_entrance"}:
            parking.append(entry)
        if tags.get("highway") in {"pedestrian", "living_street"}:
            pedestrian.append(entry)

    if not parking and not pedestrian:
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason="no_car_access_features",
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
        "parking_nearby": len(parking) > 0,
        "parking_count": len(parking),
        "pedestrian_zone_nearby": len(pedestrian) > 0,
        "pedestrian_feature_count": len(pedestrian),
        "pedestrian_zone_confirmed": False,
        "parking": parking[:10],
        "pedestrian_features": pedestrian[:10],
        "note": (
            "OSM parking/pedestrian hints only. parking_nearby=true does NOT confirm "
            "pedestrian_zone=false; hotel garage policy still needs hotelier confirmation."
        ),
    }
    return make_estimated(
        hotel_id=hotel_id,
        attribute_key=ATTRIBUTE_KEY,
        value=value,
        unit=None,
        sources=[src],
        confidence=0.55,
        method=METHOD,
        method_version=METHOD_VERSION,
        calculation_inputs={"lat": lat, "lon": lon, "radius_m": radius_m},
    )
