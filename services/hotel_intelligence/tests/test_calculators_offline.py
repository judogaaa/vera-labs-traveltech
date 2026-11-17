"""Calculator unit tests with fixture coordinates + mocked routing/OSM."""
from __future__ import annotations

from datetime import datetime, timezone

from services.hotel_intelligence.calculators.car_access import compute_car_access
from services.hotel_intelligence.calculators.family_infrastructure import (
    compute_family_infrastructure,
)
from services.hotel_intelligence.calculators.night_services import compute_night_services
from services.hotel_intelligence.calculators.noise_proxy import compute_noise_risk
from services.hotel_intelligence.calculators.walk_access import compute_walk_to_metro
from services.hotel_intelligence.models import ClaimStatus
from services.hotel_intelligence.providers.walking import WalkRoute, WalkingProvider

# Sultanahmet-ish fixture coords
LAT, LON = 41.0055, 28.9769
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


class _FakeWalk:
    def route(self, origin, dest):  # noqa: ANN001
        return WalkRoute(distance_m=650, duration_s=520, polyline="encoded", provider="mock")


class _FailWalk:
    def route(self, origin, dest):  # noqa: ANN001
        return None


def _metro_ok(lat, lon, radius_m=2500):  # noqa: ANN001
    return {
        "status": "ok",
        "error": None,
        "access_point_kind": "station_node",
        "rejected_line_candidates": 0,
        "item": {
            "lat": 41.0082,
            "lon": 28.9784,
            "name": "Sultanahmet",
            "osm_id": 1,
            "osm_type": "node",
            "uri": "https://www.openstreetmap.org/node/1",
            "tags": {"railway": "station", "station": "subway"},
        },
        "items": [],
        "fetched_at": NOW.isoformat(),
        "source_uri": "https://overpass-api.de/api/interpreter",
    }


def _metro_empty(lat, lon, radius_m=2500):  # noqa: ANN001
    return {"status": "ok", "error": None, "item": None, "items": [], "fetched_at": NOW.isoformat()}


def test_walk_to_metro_estimated_with_mock_route() -> None:
    obs = compute_walk_to_metro(
        "ist-demo-001",
        LAT,
        LON,
        walking=_FakeWalk(),  # type: ignore[arg-type]
        metro_finder=_metro_ok,
    )
    assert obs.status == ClaimStatus.ESTIMATED
    assert obs.method == "osrm_foot_route"
    assert obs.method_version == "v1"
    assert obs.value["distance_m"] == 650
    assert obs.value["duration_s"] == 520
    assert any(s.kind == "osrm" for s in obs.sources)
    assert any(s.kind == "osm" for s in obs.sources)


def test_walk_to_metro_unknown_when_routing_fails() -> None:
    obs = compute_walk_to_metro(
        "ist-demo-001",
        LAT,
        LON,
        walking=_FailWalk(),  # type: ignore[arg-type]
        metro_finder=_metro_ok,
    )
    assert obs.status == ClaimStatus.UNKNOWN
    assert obs.value is None


def test_walk_to_metro_unknown_when_no_metro() -> None:
    obs = compute_walk_to_metro(
        "ist-demo-001",
        LAT,
        LON,
        walking=_FakeWalk(),  # type: ignore[arg-type]
        metro_finder=_metro_empty,
    )
    assert obs.status == ClaimStatus.UNKNOWN


def test_noise_proxy_never_claims_db() -> None:
    def roads(lat, lon, radius_m=200):  # noqa: ANN001
        return {
            "status": "ok",
            "items": [
                {"tags": {"highway": "primary"}, "uri": "https://www.openstreetmap.org/way/1"},
                {"tags": {"amenity": "bar"}, "uri": "https://www.openstreetmap.org/node/2"},
                {"tags": {"amenity": "nightclub"}, "uri": "https://www.openstreetmap.org/node/3"},
            ],
            "fetched_at": NOW.isoformat(),
            "source_uri": "https://overpass-api.de/api/interpreter",
        }

    obs = compute_noise_risk("ist-demo-001", LAT, LON, roads_fn=roads)
    assert obs.status == ClaimStatus.ESTIMATED
    assert obs.value["risk"] in {"low", "medium", "elevated", "insufficient_data"}
    assert "dB" not in str(obs.value).lower() or "not measured" in str(obs.value).lower()
    assert "unit_note" in obs.value


def test_noise_insufficient_when_empty() -> None:
    def roads(lat, lon, radius_m=200):  # noqa: ANN001
        return {"status": "ok", "items": [], "fetched_at": NOW.isoformat(), "source_uri": "x"}

    obs = compute_noise_risk("ist-demo-001", LAT, LON, roads_fn=roads)
    assert obs.value["risk"] == "insufficient_data"


def test_night_services_uses_opening_hours() -> None:
    def pois(lat, lon, radius_m, tags):  # noqa: ANN001
        return {
            "status": "ok",
            "items": [
                {
                    "name": "Night Pharmacy",
                    "uri": "https://www.openstreetmap.org/node/9",
                    "tags": {"amenity": "pharmacy", "opening_hours": "24/7"},
                },
                {
                    "name": "Day Cafe",
                    "uri": "https://www.openstreetmap.org/node/10",
                    "tags": {"amenity": "cafe", "opening_hours": "Mo-Su 09:00-18:00"},
                },
            ],
            "fetched_at": NOW.isoformat(),
            "source_uri": "https://overpass-api.de/api/interpreter",
        }

    obs = compute_night_services("ist-demo-001", LAT, LON, pois_fn=pois)
    assert obs.status == ClaimStatus.ESTIMATED
    assert obs.value["late_or_24h_count"] == 1


def test_family_and_car_access() -> None:
    def family_pois(lat, lon, radius_m, tags):  # noqa: ANN001
        return {
            "status": "ok",
            "items": [
                {"name": "Park", "uri": "u1", "lat": LAT, "lon": LON, "tags": {"leisure": "park"}},
                {
                    "name": "Play",
                    "uri": "u2",
                    "lat": LAT,
                    "lon": LON,
                    "tags": {"leisure": "playground"},
                },
            ],
            "fetched_at": NOW.isoformat(),
            "source_uri": "x",
        }

    def car_pois(lat, lon, radius_m, tags):  # noqa: ANN001
        return {
            "status": "ok",
            "items": [
                {"name": None, "uri": "u3", "tags": {"amenity": "parking"}},
                {"name": None, "uri": "u4", "tags": {"highway": "pedestrian"}},
            ],
            "fetched_at": NOW.isoformat(),
            "source_uri": "x",
        }

    fam = compute_family_infrastructure("ist-demo-001", LAT, LON, pois_fn=family_pois)
    assert fam.value["playground_count"] == 1
    assert fam.value["park_count"] == 1

    car = compute_car_access("ist-demo-001", LAT, LON, pois_fn=car_pois)
    assert car.value["parking_nearby"] is True
    assert car.value["pedestrian_zone_nearby"] is True


def test_walking_provider_returns_none_on_failure(monkeypatch) -> None:
    class Boom:
        def build_route(self, *a, **k):  # noqa: ANN002, ANN003
            raise RuntimeError("down")

    provider = WalkingProvider(routing=Boom())  # type: ignore[arg-type]
    assert provider.route((LAT, LON), (LAT + 0.01, LON + 0.01)) is None
