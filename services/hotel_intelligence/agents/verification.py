"""VerificationAgent: detect conflicts via resolve_observations; never invents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..evidence import resolve_observations
from ..models import AttributeObservation, AttributeScope, ClaimStatus
from ..store import IntelligenceStore
from .research import AgentTrace


class VerificationAgent:
    name = "verification"

    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def check_hotel_attribute(
        self,
        hotel_id: str,
        attribute_key: str,
        *,
        scope: AttributeScope | None = None,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], AgentTrace]:
        trace = AgentTrace(agent=self.name)
        at = now or datetime.now(timezone.utc)
        rows = self.store.list_observations(hotel_id, attribute_key)
        if scope is not None:
            rows = [
                r
                for r in rows
                if r.scope.kind == scope.kind
                and (r.scope.identifier or "").lower()
                == (scope.identifier or "").lower()
            ]
        else:
            # Default: hotel-level scope only for conflict grouping
            rows = [r for r in rows if r.scope.kind == "hotel"]

        if not rows:
            result = {
                "status": ClaimStatus.UNKNOWN.value,
                "reason": "no_observations",
                "preferred_observation_id": None,
                "observation_ids": [],
                "conflict_id": None,
            }
            trace.add("empty", attribute_key=attribute_key)
            return result, trace

        # Group by exact scope
        by_scope: dict[str, list[AttributeObservation]] = {}
        for r in rows:
            key = f"{r.scope.kind}:{r.scope.identifier or ''}"
            by_scope.setdefault(key, []).append(r)

        # Check each scope group; surface first conflict
        conflict_id = None
        preferred = None
        status = ClaimStatus.UNKNOWN
        reason = "no_fresh_claim"
        all_ids: list[str] = []
        for group in by_scope.values():
            resolution = resolve_observations(group, now=at)
            all_ids.extend(resolution.observation_ids)
            if resolution.status == ClaimStatus.CONFLICTED:
                conflict_id = self.store.record_conflict(
                    hotel_id,
                    attribute_key,
                    resolution.observation_ids,
                    resolution.reason,
                )
                status = ClaimStatus.CONFLICTED
                reason = resolution.reason
                preferred = None
                trace.add(
                    "conflict",
                    conflict_id=conflict_id,
                    observation_ids=resolution.observation_ids,
                )
                break
            if resolution.status in {
                ClaimStatus.VERIFIED,
                ClaimStatus.ESTIMATED,
                ClaimStatus.UNCONFIRMED,
            }:
                status = resolution.status
                preferred = resolution.preferred_observation_id
                reason = resolution.reason
                trace.add(
                    "resolved",
                    status=status.value,
                    preferred=preferred,
                )

        return {
            "status": status.value,
            "reason": reason,
            "preferred_observation_id": preferred,
            "observation_ids": all_ids,
            "conflict_id": conflict_id,
        }, trace
