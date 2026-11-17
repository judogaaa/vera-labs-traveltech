"""Thin foot-routing wrapper around trip_planner OsrmRoutingProvider.

Never invents distance or duration: returns None on failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.trip_planner.models import LatLon
from services.trip_planner.providers.base import ProviderError
from services.trip_planner.providers.osrm import OsrmRoutingProvider


@dataclass
class WalkRoute:
    distance_m: int
    duration_s: int
    polyline: str | None
    provider: str = "osrm"


class WalkingProvider:
    def __init__(self, routing: OsrmRoutingProvider | None = None) -> None:
        self._routing = routing or OsrmRoutingProvider()

    def route(
        self,
        origin: tuple[float, float] | LatLon | dict[str, Any],
        dest: tuple[float, float] | LatLon | dict[str, Any],
    ) -> WalkRoute | None:
        """Return foot route or None. Never fabricates geometry."""
        try:
            o = _as_latlon(origin)
            d = _as_latlon(dest)
            result = self._routing.build_route(o, d, mode="walk")
            return WalkRoute(
                distance_m=int(result.distanceMeters),
                duration_s=int(result.durationSeconds),
                polyline=result.polyline,
                provider=result.provider or "osrm",
            )
        except (ProviderError, Exception):  # noqa: BLE001 — honest failure
            return None


def _as_latlon(point: tuple[float, float] | LatLon | dict[str, Any]) -> LatLon:
    if isinstance(point, LatLon):
        return point
    if isinstance(point, dict):
        return LatLon(lat=float(point["lat"]), lon=float(point["lon"]))
    lat, lon = point
    return LatLon(lat=float(lat), lon=float(lon))
