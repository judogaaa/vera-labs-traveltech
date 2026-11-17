from __future__ import annotations

from services.trip_planner.agent import TripPlannerAgent
from services.trip_planner.models import WishItem
from services.trip_planner.providers.fixtures import (
    FixtureGeocodingProvider,
    FixturePlacesProvider,
    FixtureRoutingProvider,
)
from services.trip_planner.store import TripStore


def _agent(tmp_path) -> TripPlannerAgent:
    return TripPlannerAgent(
        geocoding=FixtureGeocodingProvider(),
        places=FixturePlacesProvider(),
        routing=FixtureRoutingProvider(),
        store=TripStore(tmp_path / "trips"),
    )


def test_order_wishes_puts_generic_sights_last(tmp_path) -> None:
    agent = _agent(tmp_path)
    wishes = [
        WishItem(label="достопримечательности", kind="interest", category="attraction", query="достопримечательности"),
        WishItem(label="музей", kind="interest", category="museum", query="музей"),
        WishItem(label="ресторан", kind="interest", category="restaurant", query="ресторан"),
        WishItem(label="Айя-София", kind="must", category=None, query="Айя-София"),
    ]
    ordered = agent._order_wishes_for_places(wishes)
    labels = [w.label for w in ordered]
    assert labels[0] == "Айя-София"
    assert "музей" in labels[:3]
    assert "ресторан" in labels[:3]
    assert labels[-1] == "достопримечательности"


def test_generic_sights_detection(tmp_path) -> None:
    agent = _agent(tmp_path)
    assert agent._is_generic_sights_wish(
        WishItem(label="достопримечательности", kind="interest", category="attraction", query="достопримечательности")
    )
    assert not agent._is_generic_sights_wish(
        WishItem(label="музей", kind="interest", category="museum", query="музей")
    )
