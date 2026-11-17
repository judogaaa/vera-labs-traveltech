"""POIs whose opening_hours suggest 24/7 or late-night service."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

from ..models import AttributeObservation
from ..providers.osm import nearby_pois
from ._common import make_estimated, make_unknown, source

METHOD = "osm_opening_hours"
METHOD_VERSION = "v1"
ATTRIBUTE_KEY = "night_services"

_TAGS = [
    "amenity=pharmacy",
    "amenity=convenience",
    "shop=convenience",
    "amenity=fuel",
    "amenity=cafe",
    "amenity=fast_food",
    "amenity=bar",
]

_ALWAYS = re.compile(r"(?i)\b(24/?7|24\s*hours|Mo-Su\s+00:00-24:00|open\s+24)\b")
_LATE = re.compile(
    r"(?i)(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})|"
    r"(until|до)\s+(\d{1,2})"
)


def _suggests_late_or_24h(opening: str) -> str | None:
    if not opening:
        return None
    if _ALWAYS.search(opening) or "24/7" in opening.replace(" ", ""):
        return "24h"
    # closing after 23:00 or before 05:00 often indicates late service
    for m in re.finditer(r"(?i)(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", opening):
        end_h = int(m.group(3))
        start_h = int(m.group(1))
        if end_h >= 23 or end_h <= 5 or (start_h >= 18 and end_h < start_h):
            return "late"
    if re.search(r"(?i)\b(night|overnight|круглосуточ)\b", opening):
        return "late"
    return None


def compute_night_services(
    hotel_id: str,
    lat: float,
    lon: float,
    *,
    radius_m: int = 600,
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

    late: list[dict[str, Any]] = []
    unknown_hours = 0
    for item in res.get("items") or []:
        tags = item.get("tags") or {}
        oh = tags.get("opening_hours") or ""
        kind = _suggests_late_or_24h(oh)
        if kind:
            late.append(
                {
                    "name": item.get("name"),
                    "uri": item.get("uri"),
                    "opening_hours": oh,
                    "kind": kind,
                    "amenity": tags.get("amenity") or tags.get("shop"),
                }
            )
        elif not oh:
            unknown_hours += 1

    if not late and unknown_hours == 0 and not (res.get("items") or []):
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason="no_pois_in_radius",
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
    confirmed_24h = any(x.get("kind") == "24h" for x in late)
    if not late:
        # Pharmacy/cafe nearby without opening_hours ≠ night service confirmation
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason=(
                "pois_without_opening_hours"
                if unknown_hours
                else "no_late_or_24h_opening_hours"
            ),
            calculation_inputs={
                "lat": lat,
                "lon": lon,
                "radius_m": radius_m,
                "pois_without_hours": unknown_hours,
                "nearby_poi_count": len(res.get("items") or []),
            },
        )

    value = {
        "late_or_24h_count": len(late),
        "confirmed_24h": confirmed_24h,
        "pois": late[:20],
        "pois_without_hours": unknown_hours,
        "note": (
            "Only POIs with opening_hours suggesting late/24h are listed; "
            "pharmacy presence alone does not imply 24h."
        ),
    }
    conf = 0.65 if confirmed_24h else 0.55
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
