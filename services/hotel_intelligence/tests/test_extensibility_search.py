"""Extensibility: register attribute + search without editing search.py core lists."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.hotel_intelligence.attributes.definitions import build_default_registry
from services.hotel_intelligence.models import (
    AttributeObservation,
    AttributeScope,
    ClaimStatus,
    EvidenceSource,
)
from services.hotel_intelligence.registry import AttributeDefinition
from services.hotel_intelligence.search import parse_query, search_hotels
from services.hotel_intelligence.store import IntelligenceStore

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def test_late_night_pharmacy_walk_in_default_registry() -> None:
    reg = build_default_registry()
    assert "late_night_pharmacy_walk" in reg.keys()
    d = reg.get("late_night_pharmacy_walk")
    assert d.is_geo is True
    assert d.calculator_tool == "late_night_pharmacy_walk_calc"
    assert d.matcher == "pharmacy_walk"
    assert reg.can_attempt_computation("late_night_pharmacy_walk")


def test_register_custom_attr_searchable_without_editing_search(
    tmp_store: IntelligenceStore,
) -> None:
    reg = build_default_registry()
    reg.add(
        AttributeDefinition(
            key="rooftop_pool",
            description="Whether the hotel has a rooftop pool for guests",
            value_type="boolean",
            needed_tools=[],
            ttl_days=30,
            intent_patterns=[r"(?i)rooftop\s+pool|бассейн\s+на\s+крыше"],
            default_role="should",
            matcher="boolean_true",
            constraint_defaults={"equals": True},
        )
    )
    req = parse_query("отель с rooftop pool", registry=reg)
    assert any(r.key == "rooftop_pool" for r in req)

    tmp_store.upsert_hotel({"hotel_id": "h1", "name": "A", "lat": 41.0, "lon": 29.0})
    tmp_store.append_observation(
        AttributeObservation(
            observation_id="rp1",
            hotel_id="h1",
            attribute_key="rooftop_pool",
            scope=AttributeScope(kind="hotel"),
            value=True,
            status=ClaimStatus.UNCONFIRMED,
            sources=[
                EvidenceSource(
                    kind="hotelier_simulated",
                    uri="demo://x",
                    fetched_at=NOW,
                )
            ],
            confidence=0.5,
            observed_at=NOW,
            valid_until=NOW + timedelta(days=30),
            method="test",
            method_version="v1",
        )
    )
    out = search_hotels(tmp_store, "rooftop pool", registry=reg, prefer_gigachat=False)
    assert out["results"][0]["matched"]
    assert out["results"][0]["matched"][0]["attribute_key"] == "rooftop_pool"


def test_blackout_room_scope_disclosed(tmp_store: IntelligenceStore) -> None:
    tmp_store.upsert_hotel({"hotel_id": "h2", "name": "B", "lat": 41.0, "lon": 29.0})
    tmp_store.append_observation(
        AttributeObservation(
            observation_id="bo1",
            hotel_id="h2",
            attribute_key="blackout_curtains",
            scope=AttributeScope(kind="room_type", identifier="Deluxe"),
            value=True,
            status=ClaimStatus.UNCONFIRMED,
            sources=[
                EvidenceSource(
                    kind="hotelier_simulated",
                    uri="demo://y",
                    fetched_at=NOW,
                )
            ],
            confidence=0.55,
            observed_at=NOW,
            valid_until=NOW + timedelta(days=30),
            method="test",
            method_version="v1",
        )
    )
    out = search_hotels(tmp_store, "Deluxe blackout curtains", prefer_gigachat=False)
    hit = out["results"][0]
    assert hit["matched"]
    m = hit["matched"][0]
    assert m.get("scope", {}).get("kind") == "room_type"
    assert m.get("hotel_wide") is False
    assert "not whole hotel" in m.get("detail", "")


def test_negation_clubs_prefers_non_elevated(tmp_store: IntelligenceStore) -> None:
    req = parse_query("отель не возле клубов")
    noise = next(r for r in req if r.key == "external_noise_risk")
    assert "elevated" in (noise.constraint.get("reject_risk") or [])
    assert noise.constraint.get("reject_nightclub") is True
