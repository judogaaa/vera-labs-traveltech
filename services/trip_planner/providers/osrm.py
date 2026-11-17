"""OSRM routing with profile-correct public servers.

project-osrm.org serves the *car* graph under every profile name (foot ≈ 35 km/h).
We therefore call FOSSGIS profile-specific instances for walk/car geometry + timing.
"""
from __future__ import annotations

import os

import httpx

from .. import config
from ..models import LatLon
from .base import ProviderError, RouteResult, RoutingProvider

# FOSSGIS hosts real per-mode extracts. Path still uses /route/v1/driving/…
# (OSRM URL convention); the *instance* selects the profile.
_DEFAULT_FOOT = "https://routing.openstreetmap.de/routed-foot"
_DEFAULT_CAR = "https://routing.openstreetmap.de/routed-car"

# Sanity: pure walking rarely exceeds ~7 km/h city average over a full leg.
_WALK_MAX_IMPLIED_KMH = 7.0
_WALK_SPEED_MPS = 1.25  # ~4.5 km/h fallback when a server lies about foot timing


def _base_for_mode(mode: str) -> str:
    if mode == "car":
        return os.getenv("OSRM_CAR_URL", _DEFAULT_CAR).rstrip("/")
    # walk + transit (no transit graph) → foot instance
    return os.getenv("OSRM_FOOT_URL", _DEFAULT_FOOT).rstrip("/")


def _implied_kmh(distance_m: float, duration_s: float) -> float:
    if duration_s <= 0:
        return 999.0
    return (distance_m / duration_s) * 3.6


def _sanitize_walk_result(route: dict, *, mode: str) -> tuple[int, int, str | None]:
    dist = int(round(float(route["distance"])))
    dur = int(round(float(route["duration"])))
    poly = route.get("geometry")
    if mode == "walk" and dist > 0 and _implied_kmh(dist, dur) > _WALK_MAX_IMPLIED_KMH:
        # Never publish car-speed timings as walking.
        dur = max(1, int(round(dist / _WALK_SPEED_MPS)))
    return dist, dur, poly


class OsrmRoutingProvider(RoutingProvider):
    name = "osrm"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )

    def _request(self, base: str, coords: str) -> dict:
        url = f"{base}/route/v1/driving/{coords}"
        try:
            resp = self._client.get(url, params={"overview": "full", "geometries": "polyline"})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("route_unavailable", f"OSRM route failed: {exc}") from exc

    def build_route(self, origin: LatLon, destination: LatLon, mode: str = "walk") -> RouteResult:
        req_mode = "walk" if mode == "transit" else (mode if mode in {"walk", "car"} else "walk")
        base = _base_for_mode(req_mode)
        coords = f"{origin.lon},{origin.lat};{destination.lon},{destination.lat}"
        data = self._request(base, coords)
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ProviderError("route_unavailable", f"OSRM returned {data.get('code')}")
        route = data["routes"][0]
        dist, dur, poly = _sanitize_walk_result(route, mode=req_mode)
        return RouteResult(
            distanceMeters=dist,
            durationSeconds=dur,
            polyline=poly,
            mode=req_mode,  # type: ignore[arg-type]
            provider=self.name,
            verified=True,
        )

    def build_multi_stop_route(self, stops: list[LatLon], mode: str = "walk") -> RouteResult:
        if len(stops) < 2:
            return RouteResult(distanceMeters=0, durationSeconds=0, mode=mode, provider=self.name)
        req_mode = "walk" if mode == "transit" else (mode if mode in {"walk", "car"} else "walk")
        base = _base_for_mode(req_mode)
        coords = ";".join(f"{s.lon},{s.lat}" for s in stops)
        data = self._request(base, coords)
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ProviderError("route_unavailable", f"OSRM returned {data.get('code')}")
        route = data["routes"][0]
        dist, dur, poly = _sanitize_walk_result(route, mode=req_mode)
        return RouteResult(
            distanceMeters=dist,
            durationSeconds=dur,
            polyline=poly,
            mode=req_mode,  # type: ignore[arg-type]
            provider=self.name,
            verified=True,
        )
