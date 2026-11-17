"""Pure contract tests: no network, hotel assertions or LLM secrets."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from services.hotel_intelligence.evidence import resolve_observations
from services.hotel_intelligence.models import (
    AttributeObservation, AttributeScope, ClaimStatus, EvidenceSource,
)
from services.hotel_intelligence.registry import AttributeDefinition, AttributeRegistry

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def claim(
    observation_id: str,
    value,
    *,
    status: ClaimStatus = ClaimStatus.ESTIMATED,
    expiry_days: int = 7,
    source_kind: str = "osm",
    scope: AttributeScope | None = None,
) -> AttributeObservation:
    return AttributeObservation(
        observation_id=observation_id,
        hotel_id="istanbul-test-001",
        attribute_key="walk-to-metro",
        scope=scope or AttributeScope(kind="hotel"),
        value=value,
        unit="m",
        status=status,
        sources=[EvidenceSource(
            kind=source_kind,
            uri="https://www.openstreetmap.org/node/1",
            fetched_at=NOW,
        )],
        confidence=0.65,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=expiry_days),
        method="osrm_foot_route",
        method_version="v1",
    )


def test_unknown_must_not_contain_fake_value() -> None:
    with pytest.raises(ValidationError, match="Unknown cannot"):
        claim("a", "quiet", status=ClaimStatus.UNKNOWN)


def test_observed_value_requires_source_and_confidence() -> None:
    raw = claim("a", 650).model_dump()
    raw["sources"] = []
    with pytest.raises(ValidationError, match="source evidence"):
        AttributeObservation.model_validate(raw)
    raw = claim("a", 650).model_dump()
    raw["confidence"] = None
    with pytest.raises(ValidationError, match="confidence"):
        AttributeObservation.model_validate(raw)


def test_simulated_hotelier_alone_cannot_verify() -> None:
    with pytest.raises(ValidationError, match="simulated"):
        claim("a", True, status=ClaimStatus.VERIFIED, source_kind="hotelier_simulated")


def test_room_scope_requires_identifier() -> None:
    with pytest.raises(ValidationError):
        AttributeScope(kind="room")


def test_conflicting_fresh_values_are_not_silently_overwritten() -> None:
    resolution = resolve_observations([claim("a", 650), claim("b", 1100)], now=NOW)
    assert resolution.status == ClaimStatus.CONFLICTED
    assert set(resolution.observation_ids) == {"a", "b"}
    assert resolution.preferred_observation_id is None


def test_stale_value_not_accepted_as_fresh() -> None:
    resolution = resolve_observations(
        [claim("a", 500, expiry_days=1)],
        now=NOW + timedelta(days=3),
    )
    assert resolution.status == ClaimStatus.STALE


def test_agreeing_claims_keep_provenance() -> None:
    resolution = resolve_observations(
        [claim("a", 650), claim("b", 650, status=ClaimStatus.VERIFIED)], now=NOW,
    )
    assert resolution.status == ClaimStatus.VERIFIED
    assert resolution.preferred_observation_id == "b"
    assert resolution.observation_ids == ["a", "b"]


def test_different_room_scopes_cannot_be_merged() -> None:
    with pytest.raises(ValueError, match="unrelated"):
        resolve_observations([
            claim("a", True, scope=AttributeScope(kind="room", identifier="101")),
            claim("b", False, scope=AttributeScope(kind="room", identifier="102")),
        ], now=NOW)


def test_registry_extends_without_engine_rewrite() -> None:
    reg = AttributeRegistry()
    reg.add(AttributeDefinition(
        key="late-night-pharmacy",
        description="Whether a pharmacy is open during the night near the hotel",
        value_type="boolean",
        needed_tools=["osm_opening_hours"],
        hotelier_question=None,
        ttl_days=7,
    ))
    assert reg.keys() == ["late-night-pharmacy"]
    assert reg.can_attempt_computation("late-night-pharmacy") is False
    assert reg.missing_tools("late-night-pharmacy") == ["osm_opening_hours"]
    with pytest.raises(TypeError, match="callables"):
        reg.register_tool("osm_opening_hours", None)  # type: ignore[arg-type]
    reg.register_tool("osm_opening_hours", lambda hotel_id: {"hotel_id": hotel_id})
    assert reg.can_attempt_computation("late-night-pharmacy") is True
    assert reg.get_tool("osm_opening_hours")("demo") == {"hotel_id": "demo"}
    with pytest.raises(ValueError, match="Duplicate"):
        reg.add(reg.get("late-night-pharmacy"))
