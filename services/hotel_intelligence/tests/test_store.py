"""Append-only store behaviour."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.hotel_intelligence.models import (
    AttributeObservation,
    AttributeScope,
    ClaimStatus,
    EvidenceSource,
)
from services.hotel_intelligence.store import IntelligenceStore

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def _obs(oid: str, hotel_id: str, key: str, value) -> AttributeObservation:
    return AttributeObservation(
        observation_id=oid,
        hotel_id=hotel_id,
        attribute_key=key,
        scope=AttributeScope(kind="hotel"),
        value=value,
        unit=None,
        status=ClaimStatus.ESTIMATED,
        sources=[
            EvidenceSource(kind="osm", uri="https://www.openstreetmap.org/node/1", fetched_at=NOW)
        ],
        confidence=0.6,
        observed_at=NOW,
        valid_until=NOW + timedelta(days=7),
        method="test",
        method_version="v1",
    )


def test_upsert_and_list_hotels(tmp_store: IntelligenceStore, sample_hotel: dict) -> None:
    hid = tmp_store.upsert_hotel(sample_hotel)
    assert hid == "ist-demo-001"
    assert tmp_store.get_hotel(hid)["name"] == sample_hotel["name"]
    assert len(tmp_store.list_hotels()) == 1


def test_append_observations_are_append_only(tmp_store: IntelligenceStore, sample_hotel: dict) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    tmp_store.append_observation(_obs("o1", "ist-demo-001", "external_noise_risk", {"risk": "low"}))
    tmp_store.append_observation(_obs("o2", "ist-demo-001", "external_noise_risk", {"risk": "elevated"}))
    rows = tmp_store.list_observations("ist-demo-001", "external_noise_risk")
    assert [r.observation_id for r in rows] == ["o1", "o2"]


def test_questions_answers_conflicts(tmp_store: IntelligenceStore, sample_hotel: dict) -> None:
    tmp_store.upsert_hotel(sample_hotel)
    qid = tmp_store.create_question(
        "ist-demo-001",
        "blackout_curtains",
        "Есть ли blackout?",
    )
    aid = tmp_store.answer_question(qid, "Да, в Deluxe есть блэкаут", source_kind="hotelier_simulated")
    assert aid.startswith("a_")
    qs = tmp_store.list_questions("ist-demo-001")
    assert qs[0]["status"] == "answered"
    assert qs[0]["answers"][0]["raw_text"].startswith("Да")

    cid = tmp_store.record_conflict(
        "ist-demo-001", "external_noise_risk", ["o1", "o2"], "incompatible_fresh_claims"
    )
    tmp_store.resolve_conflict(cid, note="prefer o1", preferred_observation_id="o1")
    conflicts = tmp_store.list_conflicts("ist-demo-001")
    assert conflicts[0]["status"] == "resolved"


def test_seed_from_demo_dir(tmp_path: Path, sample_hotel: dict) -> None:
    demo = tmp_path / "demo"
    demo.mkdir()
    (demo / "hotels.json").write_text(
        json.dumps({"hotels": [sample_hotel]}, ensure_ascii=False),
        encoding="utf-8",
    )
    obs = _obs("seed1", "ist-demo-001", "walk_to_metro", {"distance_m": 400, "duration_s": 320})
    (demo / "observations.jsonl").write_text(obs.model_dump_json() + "\n", encoding="utf-8")
    store = IntelligenceStore(db_path=tmp_path / "seed.sqlite")
    counts = store.seed_from_demo_dir(demo)
    assert counts == {"hotels": 1, "observations": 1}
    assert store.list_observations("ist-demo-001")[0].observation_id == "seed1"
    store.close()
