"""Negative security cases for hotel-intelligence write endpoints."""
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

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
WRITE = {"X-Write-Token": TEST_WRITE_TOKEN, "X-Demo-Mutation": "1"}


def _client(store: IntelligenceStore) -> TestClient:
    reset_enrich_limiter(max_per_min=10)
    orch = IntelligenceOrchestrator(store, build_default_registry())
    reset_singletons(store=store, orchestrator=orch)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_write_without_auth_rejected(tmp_store: IntelligenceStore, sample_hotel: dict) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    for path, body in [
        ("/api/hotel-intelligence/bootstrap", None),
        ("/api/hotel-intelligence/enrich", {"hotel_id": "ist-demo-001"}),
        (
            "/api/hotel-intelligence/attributes",
            {
                "key": "extra_attr_x",
                "description": "An extra attribute for negative auth test",
                "value_type": "boolean",
                "ttl_days": 7,
            },
        ),
    ]:
        if body is None:
            resp = client.post(path)
        else:
            resp = client.post(path, json=body)
        assert resp.status_code == 401, path


def test_demo_mutation_header_alone_insufficient(
    tmp_store: IntelligenceStore, sample_hotel: dict
) -> None:
    """Public frontend cannot escalate with only X-Demo-Mutation: 1."""
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    resp = client.post(
        "/api/hotel-intelligence/enrich",
        headers={"X-Demo-Mutation": "1"},
        json={"hotel_id": "ist-demo-001"},
    )
    assert resp.status_code == 403
    assert "insufficient" in resp.json()["detail"]


def test_write_token_not_configured_rejects(
    tmp_store: IntelligenceStore, sample_hotel: dict, monkeypatch
) -> None:
    monkeypatch.setattr(
        "services.hotel_intelligence.config.HOTEL_INTELLIGENCE_WRITE_TOKEN", ""
    )
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    resp = client.post(
        "/api/hotel-intelligence/enrich",
        headers={"X-Write-Token": "anything", "X-Demo-Mutation": "1"},
        json={"hotel_id": "ist-demo-001"},
    )
    assert resp.status_code == 401
    assert "not_configured" in resp.json()["detail"]


def test_simulated_false_forbidden_in_demo(
    tmp_store: IntelligenceStore, sample_hotel: dict
) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    qid = tmp_store.create_question("ist-demo-001", "blackout_curtains", "blackout?")
    client = _client(tmp_store)
    resp = client.post(
        f"/api/hotel-intelligence/hotelier/questions/{qid}/answer",
        headers=WRITE,
        json={"raw_text": "Да, есть blackout", "simulated": False},
    )
    assert resp.status_code == 403
    assert "simulated" in resp.json()["detail"]


def test_bootstrap_rejects_client_demo_dir(
    tmp_store: IntelligenceStore, sample_hotel: dict
) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    resp = client.post(
        "/api/hotel-intelligence/bootstrap?demo_dir=../../etc/passwd",
        headers=WRITE,
    )
    assert resp.status_code == 400
    assert "demo_dir" in resp.json()["detail"]


def test_enrich_rate_limit(tmp_store: IntelligenceStore, sample_hotel: dict, monkeypatch) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    reset_enrich_limiter(max_per_min=2)

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

    r1 = client.post(
        "/api/hotel-intelligence/enrich",
        headers=WRITE,
        json={"hotel_id": "ist-demo-001"},
    )
    r2 = client.post(
        "/api/hotel-intelligence/enrich",
        headers=WRITE,
        json={"hotel_id": "ist-demo-001"},
    )
    r3 = client.post(
        "/api/hotel-intelligence/enrich",
        headers=WRITE,
        json={"hotel_id": "ist-demo-001"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


def test_conflict_preferred_must_exist_on_conflict(
    tmp_store: IntelligenceStore, sample_hotel: dict
) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    obs = AttributeObservation(
        observation_id="real_obs",
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
        valid_until=NOW + timedelta(days=3),
        method="t",
        method_version="v1",
    )
    tmp_store.append_observation(obs)
    cid = tmp_store.record_conflict(
        "ist-demo-001", "external_noise_risk", ["real_obs"], "test"
    )
    client = _client(tmp_store)

    # Not listed on conflict
    bad = client.post(
        f"/api/hotel-intelligence/conflicts/{cid}/resolve",
        headers=WRITE,
        json={"preferred_observation_id": "not_on_conflict"},
    )
    assert bad.status_code == 400

    # Listed but missing from store
    cid2 = tmp_store.record_conflict(
        "ist-demo-001", "external_noise_risk", ["ghost_obs"], "test2"
    )
    ghost = client.post(
        f"/api/hotel-intelligence/conflicts/{cid2}/resolve",
        headers=WRITE,
        json={"preferred_observation_id": "ghost_obs"},
    )
    assert ghost.status_code == 400


def test_demo_session_cookie_authorizes_loopback_write(
    tmp_store: IntelligenceStore, sample_hotel: dict, monkeypatch
) -> None:
    """HttpOnly demo session (no VITE token) can authorize enrich on loopback."""
    monkeypatch.setattr("services.hotel_intelligence.config.DEMO_MODE", True)
    tmp_store.upsert_hotel(sample_hotel)

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
    reset_enrich_limiter(max_per_min=10)
    reset_singletons(
        store=tmp_store,
        orchestrator=IntelligenceOrchestrator(tmp_store, build_default_registry()),
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    sess = client.post("/api/hotel-intelligence/demo/session")
    assert sess.status_code == 200
    assert sess.json()["ok"] is True

    # No X-Write-Token — cookie alone after session mint
    resp = client.post(
        "/api/hotel-intelligence/enrich",
        headers={"Origin": "http://127.0.0.1:5173", "X-Demo-Mutation": "1"},
        json={"hotel_id": "ist-demo-001"},
    )
    assert resp.status_code == 200


def test_stranger_without_session_or_token_rejected(
    tmp_store: IntelligenceStore, sample_hotel: dict
) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    resp = client.post(
        "/api/hotel-intelligence/enrich",
        headers={"Origin": "http://evil.example", "X-Demo-Mutation": "1"},
        json={"hotel_id": "ist-demo-001"},
    )
    assert resp.status_code in (401, 403)


def test_frontend_bundle_must_not_reference_vite_write_token() -> None:
    """Guardrail: never reintroduce VITE_HI_WRITE_TOKEN into the SPA client."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    api_ts = (root / "src" / "features" / "hotelIntelligence" / "api.ts").read_text(
        encoding="utf-8"
    )
    assert "VITE_HI_WRITE_TOKEN" not in api_ts
    example = (root / ".env.example").read_text(encoding="utf-8")
    assert "VITE_HI_WRITE_TOKEN" not in example


def test_hotelier_answer_wrong_hotel_forbidden(
    tmp_store: IntelligenceStore, sample_hotel: dict
) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    tmp_store.upsert_hotel(
        {
            "hotel_id": "other-hotel",
            "name": "Other",
            "lat": 41.0,
            "lon": 29.0,
        }
    )
    qid = tmp_store.create_question("ist-demo-001", "blackout_curtains", "q?")
    client = _client(tmp_store)
    resp = client.post(
        f"/api/hotel-intelligence/hotelier/questions/{qid}/answer",
        headers=WRITE,
        json={
            "raw_text": "Да, blackout есть",
            "simulated": True,
            "hotel_id": "other-hotel",
        },
    )
    assert resp.status_code == 403
    assert "wrong_hotel" in resp.json()["detail"]


def test_demo_session_disabled_without_demo_mode(
    tmp_store: IntelligenceStore, monkeypatch
) -> None:
    monkeypatch.setattr("services.hotel_intelligence.config.DEMO_MODE", False)
    client = _client(tmp_store)
    resp = client.post("/api/hotel-intelligence/demo/session")
    assert resp.status_code == 403
    assert "demo_mode_disabled" in resp.json()["detail"]


def test_demo_session_forbidden_with_public_xff(
    tmp_store: IntelligenceStore, monkeypatch
) -> None:
    """Proxy claiming a public client must not mint demo sessions."""
    monkeypatch.setattr("services.hotel_intelligence.config.DEMO_MODE", True)
    client = _client(tmp_store)
    resp = client.post(
        "/api/hotel-intelligence/demo/session",
        headers={"X-Forwarded-For": "203.0.113.50"},
    )
    assert resp.status_code == 403
    assert "proxy" in resp.json()["detail"]


def test_expired_demo_cookie_rejected(
    tmp_store: IntelligenceStore, sample_hotel: dict, monkeypatch
) -> None:
    from services.hotel_intelligence import security as sec
    from services.hotel_intelligence.tests.conftest import TEST_WRITE_TOKEN

    monkeypatch.setattr("services.hotel_intelligence.config.DEMO_MODE", True)
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)

    expired = sec.mint_demo_session_value(secret=TEST_WRITE_TOKEN, ttl=-10)
    assert not sec.verify_demo_session_value(expired, secret=TEST_WRITE_TOKEN)

    client.cookies.set(sec.DEMO_SESSION_COOKIE, expired, path="/api/hotel-intelligence")
    resp = client.post(
        "/api/hotel-intelligence/enrich",
        headers={"Origin": "http://127.0.0.1:5173"},
        json={"hotel_id": "ist-demo-001"},
    )
    assert resp.status_code == 401


def test_csrf_bad_origin_with_valid_cookie(
    tmp_store: IntelligenceStore, sample_hotel: dict, monkeypatch
) -> None:
    monkeypatch.setattr("services.hotel_intelligence.config.DEMO_MODE", True)
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    assert client.post("/api/hotel-intelligence/demo/session").status_code == 200
    resp = client.post(
        "/api/hotel-intelligence/enrich",
        headers={"Origin": "https://evil.example"},
        json={"hotel_id": "ist-demo-001"},
    )
    assert resp.status_code == 403
    assert "csrf" in resp.json()["detail"]


def test_missing_session_repeated_writes_stay_401(
    tmp_store: IntelligenceStore, sample_hotel: dict
) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    client = _client(tmp_store)
    for _ in range(3):
        resp = client.post(
            "/api/hotel-intelligence/enrich",
            json={"hotel_id": "ist-demo-001"},
        )
        assert resp.status_code == 401
