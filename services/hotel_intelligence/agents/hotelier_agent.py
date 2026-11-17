"""HotelierAgent: create questions and turn free-text answers into observations.

Simulated answers are always hotelier_simulated and cannot alone verify.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from ..models import AttributeObservation, AttributeScope, ClaimStatus, EvidenceSource
from ..providers.hotelier import extract_claims, simulate_hotelier_answer
from ..registry import AttributeRegistry
from ..store import IntelligenceStore
from .research import AgentTrace
from .verification import VerificationAgent


class HotelierAgent:
    name = "hotelier"

    def __init__(self, store: IntelligenceStore, registry: AttributeRegistry) -> None:
        self.store = store
        self.registry = registry
        self.verification = VerificationAgent(store)

    def ensure_questions(
        self,
        hotel_id: str,
        attribute_keys: list[str],
    ) -> tuple[list[str], AgentTrace]:
        trace = AgentTrace(agent=self.name)
        created: list[str] = []
        existing = {
            (q["attribute_key"], q["status"])
            for q in self.store.list_questions(hotel_id)
        }
        for key in attribute_keys:
            try:
                definition = self.registry.get(key)
            except KeyError:
                continue
            if not definition.hotelier_question:
                continue
            if any(k == key and st == "open" for k, st in existing):
                trace.add("question_already_open", attribute_key=key)
                continue
            qid = self.store.create_question(
                hotel_id,
                key,
                definition.hotelier_question,
            )
            created.append(qid)
            trace.add("question_created", question_id=qid, attribute_key=key)
        return created, trace

    def answer(
        self,
        question_id: str,
        raw_text: str,
        *,
        simulated: bool = True,
        allow_gigachat: bool = False,
    ) -> tuple[list[AttributeObservation], AgentTrace]:
        trace = AgentTrace(agent=self.name)
        questions = [
            q for q in self.store.list_questions() if q["question_id"] == question_id
        ]
        if not questions:
            raise KeyError(f"Unknown question: {question_id}")
        question = questions[0]
        hotel_id = question["hotel_id"]
        attribute_key = question["attribute_key"]

        extraction = extract_claims(
            raw_text,
            attribute_hints=[attribute_key],
            allow_gigachat=allow_gigachat,
        )
        source_kind = "hotelier_simulated" if simulated else "hotelier"
        self.store.answer_question(
            question_id,
            raw_text,
            source_kind=source_kind,
            extraction={
                "method": extraction.method,
                "method_detail": extraction.method_detail,
                "claims": [
                    {
                        "attribute_key": c.attribute_key,
                        "value": c.value,
                        "scope_kind": c.scope_kind,
                        "scope_identifier": c.scope_identifier,
                        "confidence": c.confidence,
                        "evidence_span": c.evidence_span,
                    }
                    for c in extraction.claims
                ],
            },
        )
        trace.add(
            "answered",
            question_id=question_id,
            source_kind=source_kind,
            method=extraction.method,
            claim_count=len(extraction.claims),
        )

        now = datetime.now(timezone.utc)
        observations: list[AttributeObservation] = []
        for claim in extraction.claims:
            scope = AttributeScope(
                kind=claim.scope_kind,
                identifier=claim.scope_identifier,
            )
            # Simulated → unconfirmed only; never verified from simulation alone.
            status = ClaimStatus.UNCONFIRMED
            obs = AttributeObservation(
                observation_id=f"obs_{uuid4().hex[:12]}",
                hotel_id=hotel_id,
                attribute_key=claim.attribute_key,
                scope=scope,
                value=claim.value,
                unit=None,
                status=status,
                sources=[
                    EvidenceSource(
                        kind=source_kind,  # type: ignore[arg-type]
                        uri=f"hotelier://question/{question_id}",
                        fetched_at=now,
                    )
                ],
                confidence=min(claim.confidence, 0.7),
                observed_at=now,
                valid_until=now + timedelta(days=90),
                method=f"hotelier_extract_{extraction.method}",
                method_version="v1",
                calculation_inputs={
                    "question_id": question_id,
                    "evidence_span": claim.evidence_span,
                    "raw_excerpt": raw_text[:500],
                    "simulated": simulated,
                },
            )
            self.store.append_observation(obs)
            observations.append(obs)
            # Detect conflicts for this exact scope (Deluxe yes vs Deluxe no, etc.)
            v_result, v_trace = self.verification.check_hotel_attribute(
                hotel_id,
                claim.attribute_key,
                scope=scope,
                now=now,
            )
            trace.steps.extend(v_trace.steps)
            if v_result.get("conflict_id"):
                trace.add(
                    "conflict_recorded",
                    conflict_id=v_result["conflict_id"],
                    attribute_key=claim.attribute_key,
                    scope=scope.model_dump(),
                )
            trace.add(
                "observation",
                observation_id=obs.observation_id,
                status=obs.status.value,
                attribute_key=obs.attribute_key,
            )

        if not observations:
            # Record honest unknown — free text did not yield a claim
            obs = AttributeObservation(
                observation_id=f"obs_{uuid4().hex[:12]}",
                hotel_id=hotel_id,
                attribute_key=attribute_key,
                scope=AttributeScope(kind="hotel"),
                value=None,
                status=ClaimStatus.UNKNOWN,
                sources=[],
                confidence=None,
                observed_at=now,
                method=f"hotelier_extract_{extraction.method}",
                method_version="v1",
                calculation_inputs={
                    "question_id": question_id,
                    "reason": "no_structured_claim",
                    "raw_excerpt": raw_text[:500],
                },
            )
            self.store.append_observation(obs)
            observations.append(obs)
            trace.add("no_claim", attribute_key=attribute_key)

        return observations, trace

    def simulate_and_answer(
        self,
        question_id: str,
        *,
        affirmative: bool = True,
    ) -> tuple[list[AttributeObservation], AgentTrace]:
        questions = [
            q for q in self.store.list_questions() if q["question_id"] == question_id
        ]
        if not questions:
            raise KeyError(f"Unknown question: {question_id}")
        text = simulate_hotelier_answer(
            questions[0]["attribute_key"], affirmative=affirmative
        )
        return self.answer(question_id, text, simulated=True)
