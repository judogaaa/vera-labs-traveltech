"""Append-only SQLite store for hotel intelligence evidence."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config
from .models import AttributeObservation
from .registry import AttributeDefinition


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat()


class IntelligenceStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 30000")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS hotels (
              hotel_id TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attribute_definitions (
              key TEXT PRIMARY KEY,
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observations (
              observation_id TEXT PRIMARY KEY,
              hotel_id TEXT NOT NULL,
              attribute_key TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_obs_hotel_attr
              ON observations(hotel_id, attribute_key);
            CREATE TABLE IF NOT EXISTS hotelier_questions (
              question_id TEXT PRIMARY KEY,
              hotel_id TEXT NOT NULL,
              attribute_key TEXT NOT NULL,
              question_text TEXT NOT NULL,
              scope_json TEXT,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hotelier_answers (
              answer_id TEXT PRIMARY KEY,
              question_id TEXT NOT NULL,
              raw_text TEXT NOT NULL,
              source_kind TEXT NOT NULL,
              extraction_json TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(question_id) REFERENCES hotelier_questions(question_id)
            );
            CREATE TABLE IF NOT EXISTS conflicts (
              conflict_id TEXT PRIMARY KEY,
              hotel_id TEXT NOT NULL,
              attribute_key TEXT NOT NULL,
              observation_ids_json TEXT NOT NULL,
              reason TEXT NOT NULL,
              status TEXT NOT NULL,
              resolution_note TEXT,
              created_at TEXT NOT NULL,
              resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_events (
              event_id TEXT PRIMARY KEY,
              event_type TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS enrichment_runs (
              run_id TEXT PRIMARY KEY,
              hotel_id TEXT,
              attributes_json TEXT NOT NULL,
              status TEXT NOT NULL,
              detail_json TEXT,
              created_at TEXT NOT NULL,
              finished_at TEXT
            );
            """
        )
        self._conn.commit()

    # ── hotels ──────────────────────────────────────────────────────────

    def upsert_hotel(self, hotel: dict[str, Any]) -> str:
        hotel_id = str(hotel.get("hotel_id") or hotel.get("id") or "").strip()
        if not hotel_id:
            raise ValueError("hotel_id required")
        payload = dict(hotel)
        payload["hotel_id"] = hotel_id
        self._conn.execute(
            """
            INSERT INTO hotels(hotel_id, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(hotel_id) DO UPDATE SET
              payload_json=excluded.payload_json,
              updated_at=excluded.updated_at
            """,
            (hotel_id, json.dumps(payload, ensure_ascii=False, default=str), _iso()),
        )
        self._conn.commit()
        self.audit("hotel_upsert", {"hotel_id": hotel_id})
        return hotel_id

    def get_hotel(self, hotel_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload_json FROM hotels WHERE hotel_id = ?", (hotel_id,)
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_hotels(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload_json FROM hotels ORDER BY hotel_id"
        ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    # ── attribute definitions ───────────────────────────────────────────

    def upsert_attribute_definition(self, definition: AttributeDefinition | dict) -> str:
        if isinstance(definition, AttributeDefinition):
            key = definition.key
            payload = definition.model_dump()
        else:
            key = str(definition["key"])
            payload = dict(definition)
        self._conn.execute(
            """
            INSERT INTO attribute_definitions(key, payload_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              payload_json=excluded.payload_json,
              updated_at=excluded.updated_at
            """,
            (key, json.dumps(payload, ensure_ascii=False), _iso()),
        )
        self._conn.commit()
        return key

    def list_attribute_definitions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT payload_json FROM attribute_definitions ORDER BY key"
        ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    # ── observations (append-only) ──────────────────────────────────────

    def append_observation(self, observation: AttributeObservation | dict) -> str:
        if isinstance(observation, dict):
            obs = AttributeObservation.model_validate(observation)
        else:
            obs = observation
        payload = obs.model_dump(mode="json")
        self._conn.execute(
            """
            INSERT INTO observations(
              observation_id, hotel_id, attribute_key, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                obs.observation_id,
                obs.hotel_id,
                obs.attribute_key,
                json.dumps(payload, ensure_ascii=False, default=str),
                _iso(),
            ),
        )
        self._conn.commit()
        self.audit(
            "observation_appended",
            {
                "observation_id": obs.observation_id,
                "hotel_id": obs.hotel_id,
                "attribute_key": obs.attribute_key,
                "status": obs.status.value,
            },
        )
        return obs.observation_id

    def list_observations(
        self,
        hotel_id: str,
        attribute_key: str | None = None,
    ) -> list[AttributeObservation]:
        if attribute_key:
            rows = self._conn.execute(
                """
                SELECT payload_json FROM observations
                WHERE hotel_id = ? AND attribute_key = ?
                ORDER BY created_at
                """,
                (hotel_id, attribute_key),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT payload_json FROM observations
                WHERE hotel_id = ?
                ORDER BY created_at
                """,
                (hotel_id,),
            ).fetchall()
        return [
            AttributeObservation.model_validate(json.loads(r["payload_json"]))
            for r in rows
        ]

    def get_observation(self, observation_id: str) -> AttributeObservation | None:
        row = self._conn.execute(
            "SELECT payload_json FROM observations WHERE observation_id = ?",
            (observation_id,),
        ).fetchone()
        if not row:
            return None
        return AttributeObservation.model_validate(json.loads(row["payload_json"]))

    # ── hotelier Q&A ────────────────────────────────────────────────────

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        rows = self.list_questions()
        for q in rows:
            if q["question_id"] == question_id:
                return q
        return None

    def create_question(
        self,
        hotel_id: str,
        attribute_key: str,
        question_text: str,
        *,
        scope: dict[str, Any] | None = None,
        question_id: str | None = None,
    ) -> str:
        qid = question_id or f"q_{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            """
            INSERT INTO hotelier_questions(
              question_id, hotel_id, attribute_key, question_text,
              scope_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                qid,
                hotel_id,
                attribute_key,
                question_text,
                json.dumps(scope or {"kind": "hotel"}, ensure_ascii=False),
                _iso(),
            ),
        )
        self._conn.commit()
        self.audit(
            "hotelier_question_created",
            {"question_id": qid, "hotel_id": hotel_id, "attribute_key": attribute_key},
        )
        return qid

    def answer_question(
        self,
        question_id: str,
        raw_text: str,
        *,
        source_kind: str = "hotelier_simulated",
        extraction: dict[str, Any] | None = None,
        answer_id: str | None = None,
    ) -> str:
        row = self._conn.execute(
            "SELECT question_id FROM hotelier_questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Unknown question: {question_id}")
        aid = answer_id or f"a_{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            """
            INSERT INTO hotelier_answers(
              answer_id, question_id, raw_text, source_kind,
              extraction_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                question_id,
                raw_text,
                source_kind,
                json.dumps(extraction or {}, ensure_ascii=False, default=str),
                _iso(),
            ),
        )
        self._conn.execute(
            "UPDATE hotelier_questions SET status = 'answered' WHERE question_id = ?",
            (question_id,),
        )
        self._conn.commit()
        self.audit(
            "hotelier_answer",
            {
                "answer_id": aid,
                "question_id": question_id,
                "source_kind": source_kind,
            },
        )
        return aid

    def list_questions(
        self,
        hotel_id: str | None = None,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM hotelier_questions WHERE 1=1"
        params: list[Any] = []
        if hotel_id:
            sql += " AND hotel_id = ?"
            params.append(hotel_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at"
        rows = self._conn.execute(sql, params).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            if item.get("scope_json"):
                item["scope"] = json.loads(item.pop("scope_json"))
            else:
                item.pop("scope_json", None)
                item["scope"] = None
            answers = self._conn.execute(
                "SELECT * FROM hotelier_answers WHERE question_id = ? ORDER BY created_at",
                (item["question_id"],),
            ).fetchall()
            item["answers"] = []
            for a in answers:
                ad = dict(a)
                ad["extraction"] = json.loads(ad.pop("extraction_json") or "{}")
                item["answers"].append(ad)
            out.append(item)
        return out

    # ── conflicts ───────────────────────────────────────────────────────

    def record_conflict(
        self,
        hotel_id: str,
        attribute_key: str,
        observation_ids: Iterable[str],
        reason: str,
        *,
        conflict_id: str | None = None,
    ) -> str:
        cid = conflict_id or f"c_{uuid.uuid4().hex[:12]}"
        ids = list(observation_ids)
        self._conn.execute(
            """
            INSERT INTO conflicts(
              conflict_id, hotel_id, attribute_key, observation_ids_json,
              reason, status, resolution_note, created_at, resolved_at
            ) VALUES (?, ?, ?, ?, ?, 'open', NULL, ?, NULL)
            """,
            (
                cid,
                hotel_id,
                attribute_key,
                json.dumps(ids, ensure_ascii=False),
                reason,
                _iso(),
            ),
        )
        self._conn.commit()
        self.audit(
            "conflict_recorded",
            {
                "conflict_id": cid,
                "hotel_id": hotel_id,
                "attribute_key": attribute_key,
                "observation_ids": ids,
            },
        )
        return cid

    def list_conflicts(
        self,
        hotel_id: str | None = None,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM conflicts WHERE 1=1"
        params: list[Any] = []
        if hotel_id:
            sql += " AND hotel_id = ?"
            params.append(hotel_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at"
        rows = self._conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["observation_ids"] = json.loads(item.pop("observation_ids_json"))
            out.append(item)
        return out

    def get_conflict(self, conflict_id: str) -> dict[str, Any] | None:
        for c in self.list_conflicts():
            if c["conflict_id"] == conflict_id:
                return c
        return None

    def resolve_conflict(
        self,
        conflict_id: str,
        *,
        note: str = "",
        preferred_observation_id: str | None = None,
    ) -> None:
        row = self._conn.execute(
            "SELECT conflict_id FROM conflicts WHERE conflict_id = ?",
            (conflict_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Unknown conflict: {conflict_id}")
        resolution = note
        if preferred_observation_id:
            resolution = (
                f"{note}; preferred={preferred_observation_id}".strip("; ")
            )
        self._conn.execute(
            """
            UPDATE conflicts
            SET status = 'resolved', resolution_note = ?, resolved_at = ?
            WHERE conflict_id = ?
            """,
            (resolution, _iso(), conflict_id),
        )
        self._conn.commit()
        self.audit(
            "conflict_resolved",
            {
                "conflict_id": conflict_id,
                "note": note,
                "preferred_observation_id": preferred_observation_id,
            },
        )

    # ── audit / enrichment ──────────────────────────────────────────────

    def audit(self, event_type: str, payload: dict[str, Any]) -> str:
        eid = f"e_{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            """
            INSERT INTO audit_events(event_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (eid, event_type, json.dumps(payload, ensure_ascii=False, default=str), _iso()),
        )
        self._conn.commit()
        return eid

    def start_enrichment_run(
        self,
        hotel_id: str | None,
        attributes: list[str],
        *,
        run_id: str | None = None,
    ) -> str:
        rid = run_id or f"run_{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            """
            INSERT INTO enrichment_runs(
              run_id, hotel_id, attributes_json, status, detail_json, created_at, finished_at
            ) VALUES (?, ?, ?, 'running', NULL, ?, NULL)
            """,
            (rid, hotel_id, json.dumps(attributes, ensure_ascii=False), _iso()),
        )
        self._conn.commit()
        return rid

    def finish_enrichment_run(
        self,
        run_id: str,
        *,
        status: str = "done",
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE enrichment_runs
            SET status = ?, detail_json = ?, finished_at = ?
            WHERE run_id = ?
            """,
            (
                status,
                json.dumps(detail or {}, ensure_ascii=False, default=str),
                _iso(),
                run_id,
            ),
        )
        self._conn.commit()

    # ── seed ────────────────────────────────────────────────────────────

    def seed_from_demo_dir(self, demo_dir: Path | str | None = None) -> dict[str, int]:
        root = Path(demo_dir) if demo_dir else config.DEMO_DIR
        hotels_path = root / "hotels.json"
        obs_path = root / "observations.jsonl"
        counts = {"hotels": 0, "observations": 0}
        if hotels_path.exists():
            raw = json.loads(hotels_path.read_text(encoding="utf-8"))
            hotels = raw if isinstance(raw, list) else raw.get("hotels", [])
            for h in hotels:
                self.upsert_hotel(h)
                counts["hotels"] += 1
        if obs_path.exists():
            for line in obs_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                self.append_observation(json.loads(line))
                counts["observations"] += 1
        self.audit("seed_from_demo_dir", {"dir": str(root), **counts})
        return counts
