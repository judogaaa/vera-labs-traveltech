"""FastAPI router: /api/hotel-intelligence/* — mount-ready, isolated addon."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import config
from .bootstrap import bootstrap
from .orchestrator import IntelligenceOrchestrator
from .registry import AttributeDefinition
from .search import search_hotels
from .security import (
    enforce_hotelier_simulated,
    get_enrich_limiter,
    issue_demo_session,
    require_write_auth,
    resolve_bootstrap_demo_dir,
)
from .store import IntelligenceStore

router = APIRouter(prefix="/api/hotel-intelligence", tags=["hotel-intelligence"])

_store: IntelligenceStore | None = None
_orchestrator: IntelligenceOrchestrator | None = None


def get_store() -> IntelligenceStore:
    global _store
    if _store is None:
        _store = IntelligenceStore()
    return _store


def get_orchestrator() -> IntelligenceOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = IntelligenceOrchestrator(get_store())
    return _orchestrator


def reset_singletons(
    store: IntelligenceStore | None = None,
    orchestrator: IntelligenceOrchestrator | None = None,
) -> None:
    """Test helper to inject isolated store/orchestrator."""
    global _store, _orchestrator
    _store = store
    _orchestrator = orchestrator


class EnrichRequest(BaseModel):
    hotel_id: str
    attributes: list[str] | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)
    previous_query: str | None = None
    conversation: list[dict[str, str]] | None = None
    prefer_gigachat: bool = True
    explain: bool = False


class HotelierAnswerRequest(BaseModel):
    raw_text: str = Field(min_length=1)
    simulated: bool = True
    allow_gigachat: bool = False
    hotel_id: str | None = None


class ConflictResolveRequest(BaseModel):
    note: str = ""
    preferred_observation_id: str | None = None


class RegisterAttributeRequest(BaseModel):
    key: str
    description: str
    value_type: str
    needed_tools: list[str] = Field(default_factory=list)
    hotelier_question: str | None = None
    ttl_days: int = 30
    intent_patterns: list[str] = Field(default_factory=list)
    default_role: str = "should"
    matcher: str = "presence"
    calculator_tool: str | None = None
    is_geo: bool = False
    constraint_defaults: dict[str, Any] = Field(default_factory=dict)


@router.get("/status")
def status() -> dict[str, Any]:
    store = get_store()
    hotels = store.list_hotels()
    from services.ai.gigachat_client import get_gigachat_client

    gc = get_gigachat_client()
    return {
        "ok": True,
        "db_path": str(store.db_path),
        "demo_dir": str(config.DEMO_DIR),
        "demo_mode": config.DEMO_MODE,
        "hotels": len(hotels),
        "attributes": len(get_orchestrator().registry.keys()),
        "gigachat_configured": gc is not None,
        "write_auth": "token_or_demo_session",
        "frontend_must_not_embed_write_token": True,
    }


@router.post("/demo/session")
def demo_session(request: Request, response: Response) -> dict[str, Any]:
    """Issue HttpOnly demo write cookie (loopback + DEMO_MODE only)."""
    return issue_demo_session(request, response)


@router.post("/bootstrap")
def api_bootstrap(
    demo_dir: str | None = None,
    _auth: dict[str, Any] = Depends(require_write_auth),
) -> dict[str, Any]:
    resolve_bootstrap_demo_dir(demo_dir)
    store = get_store()
    result = bootstrap(demo_dir=None, store=store)
    reset_singletons(store=store, orchestrator=IntelligenceOrchestrator(store))
    return result


@router.get("/attributes")
def list_attributes() -> dict[str, Any]:
    orch = get_orchestrator()
    defs = [orch.registry.get(k).model_dump() for k in orch.registry.keys()]
    stored = get_store().list_attribute_definitions()
    return {"attributes": defs or stored}


@router.post("/attributes")
def register_attribute(
    body: RegisterAttributeRequest,
    _auth: dict[str, Any] = Depends(require_write_auth),
) -> dict[str, Any]:
    orch = get_orchestrator()
    definition = AttributeDefinition(**body.model_dump())
    try:
        orch.registry.add(definition)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    get_store().upsert_attribute_definition(definition)
    return {"ok": True, "attribute": definition.model_dump()}


@router.get("/hotels")
def list_hotels() -> dict[str, Any]:
    return {"hotels": get_store().list_hotels()}


@router.get("/hotels/{hotel_id}")
def get_hotel(hotel_id: str) -> dict[str, Any]:
    hotel = get_store().get_hotel(hotel_id)
    if not hotel:
        raise HTTPException(status_code=404, detail="hotel_not_found")
    return {"hotel": hotel}


@router.get("/hotels/{hotel_id}/evidence")
def hotel_evidence(hotel_id: str, attribute_key: str | None = None) -> dict[str, Any]:
    if not get_store().get_hotel(hotel_id):
        raise HTTPException(status_code=404, detail="hotel_not_found")
    obs = get_store().list_observations(hotel_id, attribute_key)
    return {
        "hotel_id": hotel_id,
        "observations": [o.model_dump(mode="json") for o in obs],
    }


@router.post("/enrich")
def enrich(
    body: EnrichRequest,
    _auth: dict[str, Any] = Depends(require_write_auth),
) -> dict[str, Any]:
    get_enrich_limiter().check()
    orch = get_orchestrator()
    try:
        result = orch.enrich_hotel(body.hotel_id, body.attributes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run_id": result.run_id,
        "hotel_id": result.hotel_id,
        "observations": [o.model_dump(mode="json") for o in result.observations],
        "questions_created": result.questions_created,
        "conflicts": result.conflicts,
        "plan": result.plan,
        "traces": result.traces,
    }


@router.post("/search")
def search(body: SearchRequest) -> dict[str, Any]:
    return search_hotels(
        get_store(),
        body.query,
        limit=body.limit,
        registry=get_orchestrator().registry,
        previous_query=body.previous_query,
        conversation=body.conversation,
        prefer_gigachat=body.prefer_gigachat,
        explain=body.explain,
    )


@router.get("/hotelier/questions")
def list_hotelier_questions(
    hotel_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return {"questions": get_store().list_questions(hotel_id, status=status)}


@router.post("/hotelier/questions/{question_id}/answer")
def answer_hotelier_question(
    question_id: str,
    body: HotelierAnswerRequest,
    auth: dict[str, Any] = Depends(require_write_auth),
) -> dict[str, Any]:
    store = get_store()
    question = store.get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="question_not_found")
    if body.hotel_id and body.hotel_id != question["hotel_id"]:
        raise HTTPException(
            status_code=403,
            detail="hotelier_answer_wrong_hotel",
        )

    simulated = enforce_hotelier_simulated(simulated=body.simulated, auth=auth)

    orch = get_orchestrator()
    try:
        observations, trace = orch.hotelier.answer(
            question_id,
            body.raw_text,
            simulated=simulated,
            allow_gigachat=body.allow_gigachat,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "question_id": question_id,
        "observations": [o.model_dump(mode="json") for o in observations],
        "trace": {"agent": trace.agent, "steps": trace.steps},
    }


@router.get("/conflicts")
def list_conflicts(
    hotel_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return {"conflicts": get_store().list_conflicts(hotel_id, status=status)}


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str,
    body: ConflictResolveRequest,
    _auth: dict[str, Any] = Depends(require_write_auth),
) -> dict[str, Any]:
    store = get_store()
    conflict = store.get_conflict(conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail="conflict_not_found")

    preferred = body.preferred_observation_id
    if preferred:
        listed = set(conflict.get("observation_ids") or [])
        if preferred not in listed:
            raise HTTPException(
                status_code=400,
                detail="preferred_observation_not_on_conflict",
            )
        if not store.get_observation(preferred):
            raise HTTPException(
                status_code=400,
                detail="preferred_observation_not_found",
            )

    try:
        store.resolve_conflict(
            conflict_id,
            note=body.note,
            preferred_observation_id=preferred,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "conflict_id": conflict_id}
