from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..models import LatLon, Place


@dataclass
class RouteResult:
    distanceMeters: int
    durationSeconds: int
    polyline: str | None = None
    mode: str = "walk"
    provider: str = ""
    verified: bool = True


@dataclass
class ProviderError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class PlacesProvider(ABC):
    name: str = "places"

    @abstractmethod
    def search_places(
        self,
        query: str,
        near: LatLon,
        radius: int = 5000,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Place]:
        raise NotImplementedError

    @abstractmethod
    def get_place_details(self, place_id: str) -> Place | None:
        raise NotImplementedError


class RoutingProvider(ABC):
    name: str = "routing"

    @abstractmethod
    def build_route(self, origin: LatLon, destination: LatLon, mode: str = "walk") -> RouteResult:
        raise NotImplementedError

    def build_multi_stop_route(self, stops: list[LatLon], mode: str = "walk") -> RouteResult:
        if len(stops) < 2:
            return RouteResult(distanceMeters=0, durationSeconds=0, mode=mode, provider=self.name)
        total_dist = 0
        total_dur = 0
        for a, b in zip(stops, stops[1:]):
            seg = self.build_route(a, b, mode=mode)
            if not seg.verified:
                raise ProviderError("route_unavailable", "Routing provider could not verify segment")
            total_dist += seg.distanceMeters
            total_dur += seg.durationSeconds
        return RouteResult(
            distanceMeters=total_dist,
            durationSeconds=total_dur,
            mode=mode,
            provider=self.name,
            verified=True,
        )


class GeocodingProvider(ABC):
    name: str = "geocoding"

    @abstractmethod
    def geocode(self, text: str) -> LatLon | None:
        raise NotImplementedError

    def geocode_candidates(self, text: str, limit: int = 5) -> list["GeocodeCandidate"]:
        """Possible matches for ambiguous names. Default: single best result."""
        ll = self.geocode(text)
        if not ll:
            return []
        return [GeocodeCandidate(lat=ll.lat, lon=ll.lon, name=text, city="", country="", kind="city")]

    @abstractmethod
    def reverse_geocode(self, lat: float, lon: float) -> dict[str, str]:
        raise NotImplementedError


@dataclass
class GeocodeCandidate:
    lat: float
    lon: float
    name: str = ""
    city: str = ""
    country: str = ""
    address: str = ""
    # "city" | "admin" | "country" | "" — how Nominatim classified the match.
    kind: str = ""
    # Nominatim importance (0..1) — major cities rank above same-name villages.
    importance: float = 0.0


@dataclass
class DebugStats:
    places_searched: int = 0
    candidates: list[dict] = field(default_factory=list)
    place_api_ms: float = 0
    route_api_ms: float = 0
    agent_ms: float = 0
    geocode_ms: float = 0
    gigachat_ms: float = 0
    # skipped | called_ok | called_empty | called_error | unavailable
    gigachat_status: str = "skipped"
    wish_coverage: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
