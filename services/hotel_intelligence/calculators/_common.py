"""Shared helpers for calculators."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..models import AttributeObservation, AttributeScope, ClaimStatus, EvidenceSource


def new_observation_id(prefix: str = "obs") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_unknown(
    *,
    hotel_id: str,
    attribute_key: str,
    method: str,
    method_version: str,
    reason: str,
    sources: list[EvidenceSource] | None = None,
    calculation_inputs: dict[str, Any] | None = None,
) -> AttributeObservation:
    now = utc_now()
    return AttributeObservation(
        observation_id=new_observation_id(),
        hotel_id=hotel_id,
        attribute_key=attribute_key,
        scope=AttributeScope(kind="hotel"),
        value=None,
        unit=None,
        status=ClaimStatus.UNKNOWN,
        sources=sources or [],
        confidence=None,
        observed_at=now,
        valid_until=None,
        method=method,
        method_version=method_version,
        calculation_inputs={"reason": reason, **(calculation_inputs or {})},
    )


def make_estimated(
    *,
    hotel_id: str,
    attribute_key: str,
    value: Any,
    unit: str | None,
    sources: list[EvidenceSource],
    confidence: float,
    method: str,
    method_version: str,
    ttl_days: int = 14,
    calculation_inputs: dict[str, Any] | None = None,
) -> AttributeObservation:
    now = utc_now()
    return AttributeObservation(
        observation_id=new_observation_id(),
        hotel_id=hotel_id,
        attribute_key=attribute_key,
        scope=AttributeScope(kind="hotel"),
        value=value,
        unit=unit,
        status=ClaimStatus.ESTIMATED,
        sources=sources,
        confidence=confidence,
        observed_at=now,
        valid_until=now + timedelta(days=ttl_days),
        method=method,
        method_version=method_version,
        calculation_inputs=calculation_inputs or {},
    )


def source(
    kind: str,
    uri: str,
    *,
    fetched_at: datetime | None = None,
) -> EvidenceSource:
    return EvidenceSource(
        kind=kind,  # type: ignore[arg-type]
        uri=uri,
        fetched_at=fetched_at or utc_now(),
    )
