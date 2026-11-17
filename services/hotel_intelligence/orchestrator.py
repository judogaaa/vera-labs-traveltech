"""Plan limited tool calls, run calculators, append observations, hotelier Qs, conflicts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agents import GeoAgent, HotelierAgent, ResearchAgent, VerificationAgent
from .attributes.definitions import build_default_registry
from .models import AttributeObservation
from .registry import AttributeRegistry
from .store import IntelligenceStore


@dataclass
class EnrichmentResult:
    run_id: str
    hotel_id: str
    observations: list[AttributeObservation] = field(default_factory=list)
    questions_created: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    traces: list[dict[str, Any]] = field(default_factory=list)
    plan: list[dict[str, Any]] = field(default_factory=list)


class IntelligenceOrchestrator:
    def __init__(
        self,
        store: IntelligenceStore,
        registry: AttributeRegistry | None = None,
        *,
        max_tool_calls: int = 8,
    ) -> None:
        self.store = store
        self.registry = registry or build_default_registry()
        self.max_tool_calls = max_tool_calls
        self.research = ResearchAgent(self.registry)
        self.geo = GeoAgent(self.registry)
        self.hotelier = HotelierAgent(store, self.registry)
        self.verification = VerificationAgent(store)

        # Persist definitions for API listing
        for key in self.registry.keys():
            self.store.upsert_attribute_definition(self.registry.get(key))

    def enrich_hotel(
        self,
        hotel_id: str,
        attribute_keys: list[str] | None = None,
        *,
        tool_overrides: dict[str, Any] | None = None,
    ) -> EnrichmentResult:
        hotel = self.store.get_hotel(hotel_id)
        if not hotel:
            raise KeyError(f"Unknown hotel: {hotel_id}")
        lat = hotel.get("lat") or hotel.get("latitude")
        lon = hotel.get("lon") or hotel.get("longitude")
        if lat is None or lon is None:
            raise ValueError(f"Hotel {hotel_id} lacks coordinates")

        keys = attribute_keys or [
            k for k in self.registry.keys() if k != "blackout_curtains"
        ] + (["blackout_curtains"] if "blackout_curtains" in self.registry.keys() else [])
        # Cap work
        keys = keys[: self.max_tool_calls]

        run_id = self.store.start_enrichment_run(hotel_id, keys)
        plan, research_trace = self.research.plan(keys)

        geo_keys = [
            p["attribute_key"]
            for p in plan
            if p["can_compute"] and p["attribute_key"] != "blackout_curtains"
        ]
        hotelier_keys = [
            p["attribute_key"]
            for p in plan
            if p.get("hotelier_question")
            and (
                not p["can_compute"]
                or p["attribute_key"] == "blackout_curtains"
                or not self._has_fresh_claim(hotel_id, p["attribute_key"])
            )
        ]

        observations, geo_trace = self.geo.compute(
            hotel_id,
            float(lat),
            float(lon),
            geo_keys,
            tool_overrides=tool_overrides,
        )
        for obs in observations:
            self.store.append_observation(obs)

        questions, hotelier_trace = self.hotelier.ensure_questions(hotel_id, hotelier_keys)

        conflict_ids: list[str] = []
        verify_traces: list[dict[str, Any]] = []
        checked = {o.attribute_key for o in observations} | set(hotelier_keys)
        for key in checked:
            result, vtrace = self.verification.check_hotel_attribute(hotel_id, key)
            verify_traces.append({"attribute_key": key, "result": result, "steps": vtrace.steps})
            if result.get("conflict_id"):
                conflict_ids.append(result["conflict_id"])

        detail = {
            "observation_ids": [o.observation_id for o in observations],
            "questions": questions,
            "conflicts": conflict_ids,
        }
        self.store.finish_enrichment_run(run_id, status="done", detail=detail)

        return EnrichmentResult(
            run_id=run_id,
            hotel_id=hotel_id,
            observations=observations,
            questions_created=questions,
            conflicts=conflict_ids,
            traces=[
                {"agent": "research", "steps": research_trace.steps},
                {"agent": "geo", "steps": geo_trace.steps},
                {"agent": "hotelier", "steps": hotelier_trace.steps},
                *verify_traces,
            ],
            plan=plan,
        )

    def _has_fresh_claim(self, hotel_id: str, attribute_key: str) -> bool:
        from datetime import datetime, timezone

        from .evidence import resolve_observations
        from .models import ClaimStatus

        rows = [
            r
            for r in self.store.list_observations(hotel_id, attribute_key)
            if r.scope.kind == "hotel"
        ]
        if not rows:
            return False
        resolution = resolve_observations(rows, now=datetime.now(timezone.utc))
        return resolution.status in {
            ClaimStatus.VERIFIED,
            ClaimStatus.ESTIMATED,
            ClaimStatus.UNCONFIRMED,
        }
