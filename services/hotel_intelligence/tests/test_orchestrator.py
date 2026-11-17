"""Orchestrator: plan → calculators → observations → hotelier questions → conflicts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.hotel_intelligence.attributes.definitions import build_default_registry
from services.hotel_intelligence.models import (
    AttributeObservation,
    AttributeScope,
    ClaimStatus,
    EvidenceSource,
)
from services.hotel_intelligence.orchestrator import IntelligenceOrchestrator
from services.hotel_intelligence.store import IntelligenceStore

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
LAT, LON = 41.0055, 28.9769


def _fake_walk_obs(hotel_id: str, **kwargs) -> AttributeObservation:  # noqa: ANN003
    return AttributeObservation(
        observation_id="obs_walk_mock",
        hotel_id=hotel_id,
        attribute_key="walk_to_metro",
        scope=AttributeScope(kind="hotel"),
        value={"distance_m": 500, "duration_s": 400, "duration_min": 6.7},
        unit="m",
        status=ClaimStatus.ESTIMATED,
        sources=[
            EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/node/1", fetched_at=NOW),
            EvidenceSource(kind="osrm", uri="https://routing.openstreetmap.de/routed-foot", fetched_at=NOW),
        ],
        confidence=0.7,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=7),
        method="osrm_foot_route",
        method_version="v1",
    )


def _fake_noise(hotel_id: str, **kwargs) -> AttributeObservation:  # noqa: ANN003
    return AttributeObservation(
        observation_id="obs_noise_mock",
        hotel_id=hotel_id,
        attribute_key="external_noise_risk",
        scope=AttributeScope(kind="hotel"),
        value={"risk": "low", "counts": {}, "unit_note": "heuristic"},
        status=ClaimStatus.ESTIMATED,
        sources=[
            EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/", fetched_at=NOW)
        ],
        confidence=0.55,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=7),
        method="osm_noise_proxy",
        method_version="v1",
    )


def test_enrich_appends_observations_and_questions(
    tmp_store: IntelligenceStore,
    sample_hotel: dict,
) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    registry = build_default_registry()
    orch = IntelligenceOrchestrator(tmp_store, registry)

    overrides = {
        "walk_to_metro_calc": _fake_walk_obs,
        "noise_risk_calc": _fake_noise,
        "osm_nearest_metro": _fake_walk_obs,
        "osrm_foot_route": _fake_walk_obs,
        "osm_roads_nearby": _fake_noise,
        "night_services_calc": lambda **kw: AttributeObservation(
            observation_id="obs_night",
            hotel_id=kw["hotel_id"],
            attribute_key="night_services",
            scope=AttributeScope(kind="hotel"),
            value={"late_or_24h_count": 0, "pois": [], "pois_without_hours": 0},
            status=ClaimStatus.ESTIMATED,
            sources=[EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/", fetched_at=NOW)],
            confidence=0.4,
            observed_at=NOW,
            valid_until=NOW + timedelta(days=7),
            method="osm_opening_hours",
            method_version="v1",
        ),
        "osm_family_pois": lambda **kw: AttributeObservation(
            observation_id="obs_fam",
            hotel_id=kw["hotel_id"],
            attribute_key="family_infrastructure",
            scope=AttributeScope(kind="hotel"),
            value={"playground_count": 1, "park_count": 0, "playgrounds": [], "parks": []},
            status=ClaimStatus.ESTIMATED,
            sources=[EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/", fetched_at=NOW)],
            confidence=0.6,
            observed_at=NOW,
            valid_until=NOW + timedelta(days=7),
            method="osm_family_infra",
            method_version="v1",
        ),
        "osm_car_access": lambda **kw: AttributeObservation(
            observation_id="obs_car",
            hotel_id=kw["hotel_id"],
            attribute_key="car_access",
            scope=AttributeScope(kind="hotel"),
            value={"parking_nearby": True, "parking_count": 1, "pedestrian_zone_nearby": False},
            status=ClaimStatus.ESTIMATED,
            sources=[EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/", fetched_at=NOW)],
            confidence=0.55,
            observed_at=NOW,
            valid_until=NOW + timedelta(days=7),
            method="osm_car_access",
            method_version="v1",
        ),
    }

    result = orch.enrich_hotel(
        "ist-demo-001",
        ["walk_to_metro", "external_noise_risk", "blackout_curtains"],
        tool_overrides=overrides,
    )
    assert result.run_id
    assert any(o.attribute_key == "walk_to_metro" for o in result.observations)
    assert any(o.attribute_key == "external_noise_risk" for o in result.observations)
    assert result.questions_created, "blackout should create a hotelier question"
    qs = tmp_store.list_questions("ist-demo-001")
    assert qs[0]["attribute_key"] == "blackout_curtains"
    assert qs[0]["status"] == "open"

    # Answer via hotelier agent
    obs, trace = orch.hotelier.simulate_and_answer(qs[0]["question_id"], affirmative=True)
    assert obs
    assert all(o.status != ClaimStatus.VERIFIED for o in obs)
    assert any(s.kind == "hotelier_simulated" for o in obs for s in o.sources if o.sources)


def test_conflict_detection(tmp_store: IntelligenceStore, sample_hotel: dict) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    for oid, risk in [("c1", "low"), ("c2", "elevated")]:
        tmp_store.append_observation(
            AttributeObservation(
                observation_id=oid,
                hotel_id="ist-demo-001",
                attribute_key="external_noise_risk",
                scope=AttributeScope(kind="hotel"),
                value={"risk": risk},
                status=ClaimStatus.ESTIMATED,
                sources=[
                    EvidenceSource(
                        kind="osm",
                        uri=f"https://www.openstreetmap.org/node/{oid}",
                        fetched_at=NOW,
                    )
                ],
                confidence=0.6,
                observed_at=NOW,
                valid_until=NOW + timedelta(days=7),
                method="osm_noise_proxy",
                method_version="v1",
            )
        )
    orch = IntelligenceOrchestrator(tmp_store)
    result, _ = orch.verification.check_hotel_attribute(
        "ist-demo-001", "external_noise_risk", now=NOW
    )
    assert result["status"] == "conflicted"
    assert result["conflict_id"]
    assert tmp_store.list_conflicts("ist-demo-001")
