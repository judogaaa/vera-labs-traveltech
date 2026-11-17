"""NL search: unknown ≠ match; ranking explanations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.hotel_intelligence.models import (
    AttributeObservation,
    AttributeScope,
    ClaimStatus,
    EvidenceSource,
)
from services.hotel_intelligence.search import parse_query, search_hotels
from services.hotel_intelligence.store import IntelligenceStore

# Use a fresh reference clock so expiration-sensitive tests work after October 2026.
NOW = datetime.now(timezone.utc)


def _est(hotel_id: str, key: str, value, oid: str) -> AttributeObservation:
    return AttributeObservation(
        observation_id=oid,
        hotel_id=hotel_id,
        attribute_key=key,
        scope=AttributeScope(kind="hotel"),
        value=value,
        status=ClaimStatus.ESTIMATED,
        sources=[EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/", fetched_at=NOW)],
        confidence=0.7,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=7),
        method="test",
        method_version="v1",
    )


def test_parse_query_keywords() -> None:
    req = parse_query("Тихий номер с blackout и 10 минут пешком до метро")
    keys = {r.key for r in req}
    assert "external_noise_risk" in keys
    assert "blackout_curtains" in keys
    assert "walk_to_metro" in keys
    walk = next(r for r in req if r.key == "walk_to_metro")
    assert walk.constraint.get("max_duration_min") == 10


def test_unknown_is_not_match(tmp_store: IntelligenceStore) -> None:
    tmp_store.upsert_hotel(
        {"hotel_id": "h1", "name": "A", "lat": 41.0, "lon": 29.0}
    )
    # Only noise known; blackout unknown
    tmp_store.append_observation(
        _est("h1", "external_noise_risk", {"risk": "low"}, "o1")
    )
    out = search_hotels(tmp_store, "тихий с blackout", prefer_gigachat=False)
    hit = out["results"][0]
    assert any(m["attribute_key"] == "external_noise_risk" for m in hit["matched"])
    assert any(u["attribute_key"] == "blackout_curtains" for u in hit["unknown"])
    assert all(u.get("note") == "unknown ≠ match" for u in hit["unknown"])


def test_walk_constraint_unmatched(tmp_store: IntelligenceStore) -> None:
    tmp_store.upsert_hotel({"hotel_id": "h2", "name": "Far", "lat": 41.0, "lon": 29.0})
    tmp_store.append_observation(
        _est(
            "h2",
            "walk_to_metro",
            {"distance_m": 2000, "duration_s": 1600, "duration_min": 26.7},
            "o2",
        )
    )
    out = search_hotels(tmp_store, "10 минут пешком до метро", prefer_gigachat=False)
    hit = out["results"][0]
    assert hit["matched"] == []
    assert hit["unmatched"][0]["attribute_key"] == "walk_to_metro"


def test_elevated_noise_not_quiet(tmp_store: IntelligenceStore) -> None:
    tmp_store.upsert_hotel({"hotel_id": "h3", "name": "Noisy", "lat": 41.0, "lon": 29.0})
    tmp_store.append_observation(
        _est("h3", "external_noise_risk", {"risk": "elevated"}, "o3")
    )
    out = search_hotels(tmp_store, "тихий отель", prefer_gigachat=False)
    hit = out["results"][0]
    assert hit["unmatched"]
    assert hit["matched"] == []


def test_city_filter_kazan_excludes_istanbul(tmp_store: IntelligenceStore) -> None:
    tmp_store.upsert_hotel(
        {
            "hotel_id": "ist-1",
            "name": "Quiet Istanbul Inn",
            "city": "Istanbul",
            "lat": 41.0,
            "lon": 29.0,
        }
    )
    tmp_store.append_observation(
        _est("ist-1", "external_noise_risk", {"risk": "low"}, "n1")
    )
    tmp_store.append_observation(
        _est(
            "ist-1",
            "walk_to_metro",
            {"duration_min": 5, "access_point_kind": "entrance"},
            "w1",
        )
    )
    out = search_hotels(tmp_store, "тихий отель в Казани", prefer_gigachat=False)
    assert out["city_filter_applied"] is True
    assert out["city_match_count"] == 0
    assert out["results"] == []
    assert out["note"] == "no_hotels_in_requested_city"


def test_city_filter_istanbul_keeps_local(tmp_store: IntelligenceStore) -> None:
    tmp_store.upsert_hotel(
        {
            "hotel_id": "ist-1",
            "name": "Levent Stay",
            "city": "Istanbul",
            "lat": 41.0,
            "lon": 29.0,
        }
    )
    tmp_store.upsert_hotel(
        {
            "hotel_id": "kzn-1",
            "name": "Kazan River",
            "city": "Kazan",
            "lat": 55.7,
            "lon": 49.1,
        }
    )
    out = search_hotels(tmp_store, "отель в Стамбуле рядом с метро", prefer_gigachat=False)
    ids = {r["hotel_id"] for r in out["results"]}
    assert ids == {"ist-1"}


def test_room_blackout_not_hotel_wide(tmp_store: IntelligenceStore) -> None:
    tmp_store.upsert_hotel(
        {"hotel_id": "h4", "name": "Scoped", "city": "Istanbul", "lat": 41.0, "lon": 29.0}
    )
    obs = AttributeObservation(
        observation_id="b1",
        hotel_id="h4",
        attribute_key="blackout_curtains",
        scope=AttributeScope(kind="room_type", identifier="Deluxe"),
        value=True,
        status=ClaimStatus.UNCONFIRMED,
        sources=[
            EvidenceSource(
                kind="hotelier_simulated",
                uri="hotelier://q/1",
                fetched_at=NOW,
            )
        ],
        confidence=0.6,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=30),
        method="test",
        method_version="v1",
    )
    tmp_store.append_observation(obs)
    out = search_hotels(tmp_store, "Deluxe с плотными шторами", prefer_gigachat=False)
    hit = out["results"][0]
    matched = next(m for m in hit["matched"] if m["attribute_key"] == "blackout_curtains")
    assert matched.get("hotel_wide") is False
    assert matched.get("scope", {}).get("kind") == "room_type"
    # Standard must not inherit Deluxe confirmation
    out2 = search_hotels(tmp_store, "Standard с плотными шторами", prefer_gigachat=False)
    hit2 = out2["results"][0]
    assert not any(m["attribute_key"] == "blackout_curtains" for m in hit2["matched"])
