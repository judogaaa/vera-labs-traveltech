from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from .agent import TripPlannerAgent
from .models import (
    ChatRequest,
    LatLon,
    PlanRequest,
    PlacesSearchRequest,
    RebuildDayRequest,
    RouteCalculateRequest,
    Trip,
)
from .pdf import build_trip_pdf
from .providers.base import ProviderError
from .providers.factory import (
    get_geocoding_provider,
    get_places_provider,
    get_routing_provider,
    provider_status,
)
from .store import TripStore

router = APIRouter(tags=["trip-planner"])

_store = TripStore()
_agent: TripPlannerAgent | None = None


def get_store() -> TripStore:
    if _agent is not None:
        return _agent.store
    return _store


def get_agent() -> TripPlannerAgent:
    global _agent
    if _agent is None:
        _agent = TripPlannerAgent(
            geocoding=get_geocoding_provider(),
            places=get_places_provider(),
            routing=get_routing_provider(),
            store=_store,
        )
    return _agent


def set_agent(agent: TripPlannerAgent) -> None:
    """Test hook to inject fixture providers."""
    global _agent
    _agent = agent


def _http_from_provider(exc: ProviderError) -> HTTPException:
    status = {
        "city_not_found": 404,
        "ambiguous_destination": 422,
        "trip_not_found": 404,
        "places_unavailable": 503,
        "route_unavailable": 503,
        "geocoding_unavailable": 503,
        "not_enough_places": 422,
        "route_impossible": 422,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


@router.get("/api/trips/status")
def trips_status() -> dict[str, Any]:
    return {
        "ok": True,
        "providers": provider_status(),
        "security": {
            "auth": "none",
            "note": "GET/PATCH/DELETE /api/trips/{tripId} are unauthenticated; treat tripId as a secret capability URL.",
        },
    }


@router.post("/api/trips/plan")
def plan_trip(body: PlanRequest) -> dict[str, Any]:
    agent = get_agent()
    try:
        trip = agent.plan(body.message, hotel=body.hotel, trip_id=body.tripId)
        return {"trip": trip.model_dump()}
    except ProviderError as exc:
        raise _http_from_provider(exc) from exc


@router.post("/api/trips/plan/stream")
def plan_trip_stream(body: PlanRequest) -> StreamingResponse:
    agent = get_agent()

    def gen():
        for event in agent.plan_stream(body.message, hotel=body.hotel, trip_id=body.tripId):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/api/trips/{trip_id}/chat")
def chat_trip(trip_id: str, body: ChatRequest) -> dict[str, Any]:
    agent = get_agent()
    try:
        trip = agent.chat(trip_id, body.message)
        return {"trip": trip.model_dump()}
    except ProviderError as exc:
        raise _http_from_provider(exc) from exc


@router.get("/api/trips/{trip_id}")
def get_trip(trip_id: str) -> dict[str, Any]:
    trip = get_store().get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail={"code": "trip_not_found", "message": "Поездка не найдена"})
    return {"trip": trip.model_dump()}


@router.patch("/api/trips/{trip_id}")
def patch_trip(trip_id: str, body: dict[str, Any]) -> dict[str, Any]:
    store = get_store()
    trip = store.get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail={"code": "trip_not_found", "message": "Поездка не найдена"})
    data = trip.model_dump()
    for key in ("summary", "days", "hotel", "intent"):
        if key in body:
            data[key] = body[key]
    updated = Trip.model_validate(data)
    store.save(updated)
    return {"trip": updated.model_dump()}


@router.delete("/api/trips/{trip_id}")
def delete_trip(trip_id: str) -> dict[str, Any]:
    ok = get_store().delete(trip_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"code": "trip_not_found", "message": "Поездка не найдена"})
    return {"ok": True}


@router.post("/api/trips/{trip_id}/rebuild-day")
def rebuild_day(trip_id: str, body: RebuildDayRequest) -> dict[str, Any]:
    agent = get_agent()
    msg = body.message or f"Перестрой день {body.dayNumber}"
    try:
        trip = agent.chat(trip_id, msg)
        return {"trip": trip.model_dump()}
    except ProviderError as exc:
        raise _http_from_provider(exc) from exc


@router.get("/api/trips/{trip_id}/pdf")
def trip_pdf(
    trip_id: str,
    link: str | None = Query(default=None),
) -> Response:
    trip = get_store().get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail={"code": "trip_not_found", "message": "Поездка не найдена"})
    pdf_bytes = build_trip_pdf(trip, web_link=link)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="oh-route-{trip_id}.pdf"'},
    )


@router.post("/api/places/search")
def places_search(body: PlacesSearchRequest) -> dict[str, Any]:
    places = get_places_provider()
    try:
        results = places.search_places(
            body.query,
            LatLon(lat=body.nearLat, lon=body.nearLon),
            radius=body.radiusMeters,
            category=body.category,
        )
        return {"places": [p.model_dump() for p in results], "provider": places.name}
    except ProviderError as exc:
        raise _http_from_provider(exc) from exc


@router.post("/api/routes/calculate")
def routes_calculate(body: RouteCalculateRequest) -> dict[str, Any]:
    routing = get_routing_provider()
    try:
        result = routing.build_route(
            LatLon(lat=body.originLat, lon=body.originLon),
            LatLon(lat=body.destLat, lon=body.destLon),
            mode=body.mode,
        )
        return {
            "distanceMeters": result.distanceMeters,
            "durationSeconds": result.durationSeconds,
            "polyline": result.polyline,
            "mode": result.mode,
            "provider": result.provider,
            "verified": result.verified,
        }
    except ProviderError as exc:
        raise _http_from_provider(exc) from exc
