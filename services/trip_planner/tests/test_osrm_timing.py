from __future__ import annotations

from services.trip_planner.models import LatLon
from services.trip_planner.optimizer import _implied_kmh, _route_leg
from services.trip_planner.providers.base import ProviderError, RouteResult, RoutingProvider
from services.trip_planner.providers.osrm import _sanitize_walk_result


def test_sanitize_rejects_car_speed_as_walk() -> None:
    # 3200 m in 420 s ≈ 27 km/h — must be rewritten to pedestrian duration
    dist, dur, _poly = _sanitize_walk_result(
        {"distance": 3200, "duration": 420, "geometry": "abc"},
        mode="walk",
    )
    assert dist == 3200
    assert _implied_kmh(dist, dur) <= 7.0
    assert dur >= 2000  # ~4.5 km/h => ~42 min


def test_sanitize_leaves_car_untouched() -> None:
    dist, dur, _ = _sanitize_walk_result(
        {"distance": 3200, "duration": 420, "geometry": None},
        mode="car",
    )
    assert dist == 3200
    assert dur == 420


def test_car_speed_walk_upgrades_to_car() -> None:
    class LyingFoot(RoutingProvider):
        name = "lying"

        def build_route(self, origin, destination, mode: str = "walk"):
            if mode == "walk":
                return RouteResult(
                    distanceMeters=2900,
                    durationSeconds=300,  # 5 min — impossible on foot
                    polyline="walkpoly",
                    mode="walk",
                    provider=self.name,
                    verified=True,
                )
            return RouteResult(
                distanceMeters=3100,
                durationSeconds=480,
                polyline="carpoly",
                mode="car",
                provider=self.name,
                verified=True,
            )

    route, mode = _route_leg(
        LyingFoot(),
        LatLon(lat=55.79, lon=49.10),
        LatLon(lat=55.80, lon=49.13),
        "walk",
    )
    assert mode == "car"
    assert route.polyline == "carpoly"
    assert route.durationSeconds == 480


def test_plausible_walk_stays_walk() -> None:
    class HonestFoot(RoutingProvider):
        name = "honest"

        def build_route(self, origin, destination, mode: str = "walk"):
            return RouteResult(
                distanceMeters=900,
                durationSeconds=720,  # 12 min ≈ 4.5 km/h
                polyline="w",
                mode="walk",
                provider=self.name,
                verified=True,
            )

    route, mode = _route_leg(
        HonestFoot(),
        LatLon(lat=55.79, lon=49.10),
        LatLon(lat=55.795, lon=49.105),
        "walk",
    )
    assert mode == "walk"
    assert route.durationSeconds == 720


def test_live_fossgis_foot_is_pedestrian_speed() -> None:
    """Integration: FOSSGIS foot instance must not return car-like km/h."""
    import httpx

    try:
        url = (
            "https://routing.openstreetmap.de/routed-foot/route/v1/driving/"
            "49.106,55.796;49.140,55.810"
        )
        data = httpx.get(
            url,
            params={"overview": "false"},
            timeout=25,
            headers={"User-Agent": "OhHochu-test/1.0"},
        ).json()
    except Exception as exc:  # noqa: BLE001
        import pytest

        pytest.skip(f"FOSSGIS unavailable: {exc}")
    if data.get("code") != "Ok" or not data.get("routes"):
        import pytest

        pytest.skip(f"FOSSGIS returned {data.get('code')}")
    rt = data["routes"][0]
    kmh = (rt["distance"] / max(rt["duration"], 1)) * 3.6
    assert kmh < 10.0, f"foot profile too fast: {kmh:.1f} km/h"
