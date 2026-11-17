"""Conservative resolution: never silently overwrite contradictory attributes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .models import AttributeObservation, ClaimStatus


def _normalize_value_for_compare(obs: AttributeObservation) -> Any:
    """Treat boolean blackout shapes as equivalent (True == {has_blackout: true})."""
    value = obs.value
    if obs.attribute_key == "blackout_curtains":
        if isinstance(value, dict) and "has_blackout" in value:
            return bool(value.get("has_blackout"))
        if isinstance(value, bool):
            return value
    return value


class Resolution(BaseModel):
    status: ClaimStatus
    preferred_observation_id: str | None = None
    observation_ids: list[str] = Field(default_factory=list)
    reason: str


def resolve_observations(
    observations: Iterable[AttributeObservation],
    *,
    now: datetime | None = None,
) -> Resolution:
    """Resolve exactly one hotel + attribute + scope; keep every input ID visible.

    Fresh disagreements are conflicts even if sources have different confidence.
    Actual manual resolution and append-only persistence are future work.
    """
    rows = list(observations)
    if not rows:
        return Resolution(status=ClaimStatus.UNKNOWN, reason="no_data")

    identity = (rows[0].hotel_id, rows[0].attribute_key, rows[0].scope)
    if any((r.hotel_id, r.attribute_key, r.scope) != identity for r in rows):
        raise ValueError("Cannot resolve unrelated hotels, attributes or room scopes")

    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    ids = [r.observation_id for r in rows]
    active = [
        r for r in rows
        if r.status in {ClaimStatus.VERIFIED, ClaimStatus.ESTIMATED, ClaimStatus.UNCONFIRMED}
        and not r.is_expired(at)
    ]
    if not active:
        status = ClaimStatus.STALE if any(r.is_expired(at) for r in rows) else ClaimStatus.UNKNOWN
        return Resolution(status=status, observation_ids=ids, reason="no_fresh_claim")

    variants = {
        json.dumps(_normalize_value_for_compare(r), sort_keys=True, ensure_ascii=False, default=str)
        for r in active
    }
    if len(variants) > 1:
        return Resolution(
            status=ClaimStatus.CONFLICTED, observation_ids=ids,
            reason="incompatible_fresh_claims",
        )

    weight = {
        ClaimStatus.VERIFIED: 3,
        ClaimStatus.ESTIMATED: 2,
        ClaimStatus.UNCONFIRMED: 1,
    }
    best = max(active, key=lambda r: (weight[r.status], r.observed_at))
    return Resolution(
        status=best.status,
        preferred_observation_id=best.observation_id,
        observation_ids=ids,
        reason="consistent_fresh_claims",
    )
