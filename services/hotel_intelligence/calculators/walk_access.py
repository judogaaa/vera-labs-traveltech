"""walk_to_metro: nearest metro (OSM) + OSRM foot route."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..models import AttributeObservation
from ..providers.osm import nearest_metro
from ..providers.walking import WalkingProvider
from ._common import make_estimated, make_unknown, source


METHOD = "osrm_foot_route"
METHOD_VERSION = "v1"
ATTRIBUTE_KEY = "walk_to_metro"


def compute_walk_to_metro(
    hotel_id: str,
    lat: float,
    lon: float,
    *,
    walking: WalkingProvider | None = None,
    metro_finder: Callable[..., dict[str, Any]] | None = None,
    radius_m: int = 2500,
) -> AttributeObservation:
    finder = metro_finder or nearest_metro
    walker = walking or WalkingProvider()

    metro_res = finder(lat, lon, radius_m=radius_m)
    item_preview = metro_res.get("item") or {}
    kind = metro_res.get("access_point_kind") or (
        _infer_access_kind(item_preview) if item_preview else "none"
    )
    if metro_res.get("status") == "error" or not metro_res.get("item") or kind in {
        "none",
        None,
    }:
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason=metro_res.get("error")
            or (
                "no_verified_metro_access_point"
                if metro_res.get("rejected_line_candidates")
                else "no_metro_found"
            ),
            calculation_inputs={
                "lat": lat,
                "lon": lon,
                "radius_m": radius_m,
                "rejected_line_candidates": metro_res.get("rejected_line_candidates"),
                "access_point_kind": kind,
            },
        )

    item = metro_res["item"]
    fetched = metro_res.get("fetched_at")
    try:
        fetched_at = (
            datetime.fromisoformat(fetched.replace("Z", "+00:00"))
            if isinstance(fetched, str)
            else datetime.now(timezone.utc)
        )
    except ValueError:
        fetched_at = datetime.now(timezone.utc)

    osm_src = source(
        "osm",
        item.get("uri") or metro_res.get("source_uri") or "https://www.openstreetmap.org/",
        fetched_at=fetched_at,
    )

    route = walker.route((lat, lon), (float(item["lat"]), float(item["lon"])))
    if route is None:
        return make_unknown(
            hotel_id=hotel_id,
            attribute_key=ATTRIBUTE_KEY,
            method=METHOD,
            method_version=METHOD_VERSION,
            reason="routing_failed",
            sources=[osm_src],
            calculation_inputs={
                "lat": lat,
                "lon": lon,
                "metro": {"lat": item["lat"], "lon": item["lon"], "name": item.get("name")},
            },
        )

    osrm_src = source(
        "osrm",
        "https://routing.openstreetmap.de/routed-foot",
        fetched_at=datetime.now(timezone.utc),
    )
    access_kind = (
        metro_res.get("access_point_kind")
        or _infer_access_kind(item)
    )
    rejected = int(metro_res.get("rejected_line_candidates") or 0)
    value = {
        "distance_m": route.distance_m,
        "duration_s": route.duration_s,
        "duration_min": round(route.duration_s / 60.0, 1),
        "metro_name": item.get("name"),
        "metro_lat": item["lat"],
        "metro_lon": item["lon"],
        "metro_osm_type": item.get("osm_type"),
        "metro_osm_id": item.get("osm_id"),
        "access_point_kind": access_kind,
        "rejected_line_candidates": rejected,
        "polyline": route.polyline,
    }
    if access_kind == "unconfirmed_station":
        value["note"] = (
            "Access point is an unconfirmed station/way center — not a verified entrance."
        )
        conf = 0.4 if route.distance_m <= 1200 else 0.35
    elif access_kind == "none":
        conf = 0.3
    else:
        conf = 0.72 if route.distance_m <= 1200 else 0.6 if route.distance_m <= 2000 else 0.5
    return make_estimated(
        hotel_id=hotel_id,
        attribute_key=ATTRIBUTE_KEY,
        value=value,
        unit="m",
        sources=[osm_src, osrm_src],
        confidence=conf,
        method=METHOD,
        method_version=METHOD_VERSION,
        ttl_days=14,
        calculation_inputs={
            "origin": {"lat": lat, "lon": lon},
            "destination": {
                "lat": item["lat"],
                "lon": item["lon"],
                "osm_id": item.get("osm_id"),
                "osm_type": item.get("osm_type"),
                "access_point_kind": access_kind,
            },
            "provider": route.provider,
            "rejected_line_candidates": rejected,
        },
    )


def _infer_access_kind(item: dict[str, Any]) -> str:
    tags = item.get("tags") or {}
    osm_type = (item.get("osm_type") or "").lower()
    if tags.get("railway") == "subway_entrance":
        return "entrance"
    if osm_type == "node" and (
        tags.get("railway") == "station"
        or tags.get("station") == "subway"
        or tags.get("public_transport") == "station"
    ):
        return "station_node"
    if osm_type in {"way", "relation"} or item.get("used_way_center"):
        return "unconfirmed_station"
    return "station_node"
