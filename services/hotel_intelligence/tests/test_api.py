"""API TestClient coverage for /api/hotel-intelligence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.hotel_intelligence.api import reset_singletons, router
from services.hotel_intelligence.attributes.definitions import build_default_registry
from services.hotel_intelligence.models import (
    AttributeObservation,
    AttributeScope,
    ClaimStatus,
    EvidenceSource,
)
from services.hotel_intelligence.orchestrator import IntelligenceOrchestrator
from services.hotel_intelligence.security import reset_enrich_limiter
from services.hotel_intelligence.store import IntelligenceStore

from services.hotel_intelligence.tests.conftest import TEST_WRITE_TOKEN

# Use a fresh reference clock so expiration-sensitive tests work after October 2026.
NOW = datetime.now(timezone.utc)

WRITE_HEADERS = {"X-Write-Token": TEST_WRITE_TOKEN, "X-Demo-Mutation": "1"}


def _client(store: IntelligenceStore) -> TestClient:
    reset_enrich_limiter()
    orch = IntelligenceOrchestrator(store, build_default_registry())
    reset_singletons(store=store, orchestrator=orch)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_status_attributes_hotels(tmp_store: IntelligenceStore, sample_hotel: dict) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    st = client.get("/api/hotel-intelligence/status")
    assert st.status_code == 200
    assert st.json()["ok"] is True
    assert st.json()["hotels"] == 1

    attrs = client.get("/api/hotel-intelligence/attributes")
    assert attrs.status_code == 200
    keys = {a["key"] for a in attrs.json()["attributes"]}
    assert "walk_to_metro" in keys
    assert "blackout_curtains" in keys

    hotels = client.get("/api/hotel-intelligence/hotels")
    assert hotels.json()["hotels"][0]["hotel_id"] == "ist-demo-001"

    one = client.get("/api/hotel-intelligence/hotels/ist-demo-001")
    assert one.status_code == 200


def test_evidence_search_hotelier_conflict_flow(
    tmp_store: IntelligenceStore,
    sample_hotel: dict,
) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    o1 = AttributeObservation(
        observation_id="api_o1",
        hotel_id="ist-demo-001",
        attribute_key="external_noise_risk",
        scope=AttributeScope(kind="hotel"),
        value={"risk": "low", "unit_note": "heuristic"},
        status=ClaimStatus.ESTIMATED,
        sources=[
            EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/", fetched_at=NOW)
        ],
        confidence=0.6,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=7),
        method="osm_noise_proxy",
        method_version="v1",
    )
    tmp_store.append_observation(o1)
    client = _client(tmp_store)

    ev = client.get("/api/hotel-intelligence/hotels/ist-demo-001/evidence")
    assert ev.status_code == 200
    assert len(ev.json()["observations"]) == 1

    search = client.post(
        "/api/hotel-intelligence/search",
        json={"query": "тихий отель", "limit": 10},
    )
    assert search.status_code == 200
    assert search.json()["results"][0]["matched"]

    qid = tmp_store.create_question(
        "ist-demo-001",
        "blackout_curtains",
        "Есть ли blackout?",
    )
    ans = client.post(
        f"/api/hotel-intelligence/hotelier/questions/{qid}/answer",
        headers=WRITE_HEADERS,
        json={
            "raw_text": "Да, в Deluxe есть плотные шторы блэкаут",
            "simulated": True,
        },
    )
    assert ans.status_code == 200
    body = ans.json()
    assert body["observations"]
    assert all(o["status"] != "verified" for o in body["observations"])

    o_a = AttributeObservation(
        observation_id="conflict_a",
        hotel_id="ist-demo-001",
        attribute_key="external_noise_risk",
        scope=AttributeScope(kind="hotel"),
        value={"risk": "elevated"},
        status=ClaimStatus.ESTIMATED,
        sources=[
            EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/", fetched_at=NOW)
        ],
        confidence=0.5,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=7),
        method="test",
        method_version="v1",
    )
    o_b = AttributeObservation(
        observation_id="conflict_b",
        hotel_id="ist-demo-001",
        attribute_key="external_noise_risk",
        scope=AttributeScope(kind="hotel"),
        value={"risk": "low"},
        status=ClaimStatus.ESTIMATED,
        sources=[
            EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/", fetched_at=NOW)
        ],
        confidence=0.5,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=7),
        method="test",
        method_version="v1",
    )
    tmp_store.append_observation(o_a)
    tmp_store.append_observation(o_b)
    cid = tmp_store.record_conflict(
        "ist-demo-001", "external_noise_risk", ["conflict_a", "conflict_b"], "test"
    )
    resolved = client.post(
        f"/api/hotel-intelligence/conflicts/{cid}/resolve",
        headers=WRITE_HEADERS,
        json={"note": "keep first", "preferred_observation_id": "conflict_a"},
    )
    assert resolved.status_code == 200
    assert tmp_store.list_conflicts()[0]["status"] == "resolved"


def test_register_attribute(tmp_store: IntelligenceStore, sample_hotel: dict) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    resp = client.post(
        "/api/hotel-intelligence/attributes",
        headers=WRITE_HEADERS,
        json={
            "key": "late_night_pharmacy",
            "description": "Whether a pharmacy is open at night near the hotel",
            "value_type": "boolean",
            "needed_tools": ["osm_opening_hours"],
            "ttl_days": 7,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["attribute"]["key"] == "late_night_pharmacy"


def test_enrich_endpoint_uses_overrides_via_orchestrator_not_required(
    tmp_store: IntelligenceStore,
    sample_hotel: dict,
    monkeypatch,
) -> None:
    """Enrich without network: stub GeoAgent.compute."""
    tmp_store.upsert_hotel(sample_hotel)
    reset_enrich_limiter()

    def fake_enrich(self, hotel_id, attribute_keys=None, tool_overrides=None):  # noqa: ANN001
        from services.hotel_intelligence.orchestrator import EnrichmentResult

        run_id = self.store.start_enrichment_run(hotel_id, attribute_keys or [])
        self.store.finish_enrichment_run(run_id, status="done", detail={})
        return EnrichmentResult(
            run_id=run_id,
            hotel_id=hotel_id,
            observations=[],
            questions_created=[],
            conflicts=[],
            traces=[],
            plan=[],
        )

    monkeypatch.setattr(IntelligenceOrchestrator, "enrich_hotel", fake_enrich)
    reset_singletons(
        store=tmp_store,
        orchestrator=IntelligenceOrchestrator(tmp_store, build_default_registry()),
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.post(
        "/api/hotel-intelligence/enrich",
        headers=WRITE_HEADERS,
        json={"hotel_id": "ist-demo-001", "attributes": ["walk_to_metro"]},
    )
    assert resp.status_code == 200
    assert resp.json()["run_id"]
