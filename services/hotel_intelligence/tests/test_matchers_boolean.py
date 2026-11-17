"""boolean matcher must honour equals=true and equals=false."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.hotel_intelligence.matchers import match_constraint
from services.hotel_intelligence.models import (
    AttributeObservation,
    AttributeScope,
    ClaimStatus,
    EvidenceSource,
)
from services.hotel_intelligence.registry import AttributeDefinition

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def _obs(value) -> AttributeObservation:
    return AttributeObservation(
        observation_id="o1",
        hotel_id="h1",
        attribute_key="blackout_curtains",
        scope=AttributeScope(kind="hotel"),
        value=value,
        status=ClaimStatus.UNCONFIRMED,
        sources=[EvidenceSource(kind="hotelier_simulated", uri="demo", fetched_at=NOW)],
        confidence=0.5,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=30),
        method="t",
        method_version="v1",
    )


def _def() -> AttributeDefinition:
    return AttributeDefinition(
        key="blackout_curtains",
        description="blackout",
        value_type="boolean",
        matcher="boolean_true",
        ttl_days=30,
        constraint_defaults={"equals": True},
    )


def test_equals_true_matches_true() -> None:
    result, _ = match_constraint(_def(), _obs(True), {"equals": True})
    assert result == "match"


def test_equals_true_rejects_false() -> None:
    result, reason = match_constraint(_def(), _obs(False), {"equals": True})
    assert result == "unmatch"
    assert "false" in reason


def test_equals_false_matches_false() -> None:
    """«Standard без blackout» must match observations where blackout is absent."""
    result, reason = match_constraint(_def(), _obs(False), {"equals": False})
    assert result == "match"
    assert "false" in reason


def test_equals_false_rejects_true() -> None:
    result, reason = match_constraint(_def(), _obs(True), {"equals": False})
    assert result == "unmatch"


def test_dict_has_blackout_shape() -> None:
    result, _ = match_constraint(_def(), _obs({"has_blackout": False}), {"equals": False})
    assert result == "match"
