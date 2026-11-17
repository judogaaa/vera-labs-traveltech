"""Hotelier free-text extraction — regex first; simulation never verifies alone."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.hotel_intelligence.models import (
    AttributeObservation,
    AttributeScope,
    ClaimStatus,
    EvidenceSource,
)
from services.hotel_intelligence.providers.hotelier import (
    extract_claims,
    simulate_hotelier_answer,
)
from datetime import datetime, timezone

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def test_extract_blackout_yes() -> None:
    result = extract_claims(
        "В номерах Deluxe установлены плотные шторы блэкаут",
        attribute_hints=["blackout_curtains"],
    )
    assert result.method == "regex_rules"
    assert len(result.claims) == 1
    assert result.claims[0].value is True
    assert result.claims[0].scope_kind in {"hotel", "room_type"}


def test_extract_blackout_no() -> None:
    result = extract_claims("К сожалению, blackout-штор нет, только обычные")
    assert result.claims[0].value is False


def test_extract_blackout_no_inline_deluxe() -> None:
    result = extract_claims("Извините, в Deluxe blackout нет — ошибка.")
    assert result.claims
    assert result.claims[0].value is False
    assert (result.claims[0].scope_identifier or "").lower() == "deluxe"


def test_extract_room_scope() -> None:
    result = extract_claims("В номере 412 есть blackout curtains")
    assert result.claims
    assert result.claims[0].scope_kind == "room"
    assert result.claims[0].scope_identifier == "412"


def test_extract_multi_scope_standard_deluxe() -> None:
    result = extract_claims(
        "В Standard плотных штор нет. В Deluxe blackout есть. "
        "Номера 301-305 — семейные, шторы обычные."
    )
    assert len(result.claims) >= 2
    by_scope = {
        (c.scope_kind, (c.scope_identifier or "").lower()): c.value for c in result.claims
    }
    assert by_scope.get(("room_type", "standard")) is False
    assert by_scope.get(("room_type", "deluxe")) is True


def test_empty_text_no_claims() -> None:
    result = extract_claims("")
    assert result.method == "none"
    assert result.claims == []


def test_simulate_marked_text() -> None:
    text = simulate_hotelier_answer("blackout_curtains", affirmative=True)
    assert "блэкаут" in text.lower() or "blackout" in text.lower()


def test_simulated_cannot_set_verified() -> None:
    with pytest.raises(ValidationError, match="simulated"):
        AttributeObservation(
            observation_id="x",
            hotel_id="h",
            attribute_key="blackout_curtains",
            scope=AttributeScope(kind="hotel"),
            value=True,
            status=ClaimStatus.VERIFIED,
            sources=[
                EvidenceSource(
                    kind="hotelier_simulated",
                    uri="hotelier://q/1",
                    fetched_at=NOW,
                )
            ],
            confidence=0.9,
            observed_at=NOW,
            method="hotelier_extract_regex_rules",
            method_version="v1",
        )
