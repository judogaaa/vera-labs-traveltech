from __future__ import annotations

import json
import secrets
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from . import config
from .agent import TripPlannerAgent
from .limits import ConcurrencyGate, SlidingWindowLimiter
from .models import (
    ChatRequest,
    LatLon,
    PlanRequest,
    PlacesSearchRequest,
    RebuildDayRequest,
    RouteCalculateRequest,
    Trip,
    TripPatch,
)
from .pdf import build_trip_pdf
from .providers.base import ProviderError
from .providers.factory import (
    get_geocoding_provider,
    get_places_provider,
    get_routing_provider,
    provider_status,
)
from .session import (
    COOKIE_NAME,
    CSRF_HEADER,
    SAFE_METHODS,
    SessionRecord,
    SessionStore,
    clear_session_cookie,
    set_session_cookie,
)
from .store import TripStore, valid_trip_id

router = APIRouter(tags=["trip-planner"])

_store = TripStore()
_sessions = SessionStore()
_agent: TripPlannerAgent | None = None

_limiter = SlidingWindowLimiter()
_plan_gate = ConcurrencyGate(config.TRIP_MAX_CONCURRENT_PLANS)
_pdf_gate = ConcurrencyGate(config.TRIP_MAX_CONCURRENT_PDFS)

_RATE_10MIN = 600.0
_RATE_1MIN = 60.0


def get_store() -> TripStore:
    if _agent is not None:
        return _agent.store
    return _store


def get_session_store() -> SessionStore:
    return _sessions


def set_session_store(store: SessionStore) -> None:
    """Test hook: isolate the session registry."""
    global _sessions
    _sessions = store


def get_limiter() -> SlidingWindowLimiter:
    return _limiter


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


def _too_many(retry_after: int = 30) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={
            "code": "rate_limited",
            "message": "Слишком много запросов. Подождите и повторите.",
        },
        headers={"Retry-After": str(retry_after)},
    )


def _not_found() -> HTTPException:
    # Identical response for "does not exist", "belongs to another session"
    # and "malformed id": the API never confirms that a trip exists.
    return HTTPException(
        status_code=404,
        detail={"code": "trip_not_found", "message": "Поездка не найдена"},
    )


def _origin_allowed(request: Request) -> bool:
    """Reject cross-site browser writes even if a CSRF token leaked."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not host:
        return False
    if host in {"127.0.0.1", "localhost", "::1", "testserver"}:
        return True
    return host == (request.url.hostname or "").lower()


def _require_csrf(request: Request, record: SessionRecord) -> None:
    supplied = request.headers.get(CSRF_HEADER, "")
    if not supplied or not secrets.compare_digest(supplied, record.csrf):
        raise HTTPException(
            status_code=403,
            detail={"code": "csrf_failed", "message": "Недействительный CSRF-токен"},
        )
    if not _origin_allowed(request):
        raise HTTPException(
            status_code=403,
            detail={"code": "origin_rejected", "message": "Источник запроса не разрешён"},
        )


def require_session(request: Request, response: Response) -> SessionRecord:
    """Resolve (or mint) the signed browser session and enforce CSRF.

    A client-supplied session id is never trusted: ids come only from the
    server-side registry and are signed.  Unsafe methods require the
    per-session token returned by ``GET /api/trips/session``.
    """
    record = _sessions.resolve(request.cookies.get(COOKIE_NAME))
    created = record is None
    if record is None:
        record = _sessions.create()
    if request.method not in SAFE_METHODS:
        _require_csrf(request, record)
    if created:
        set_session_cookie(response, request, record)
    request.state.trip_session = record
    return record


def _client_ip(request: Request) -> str:
    # The demo is served directly (no trusted proxy configured), so never
    # trust X-Forwarded-For here; it would let one client rotate identities.
    return request.client.host if request.client else "unknown"


def _enforce(
    request: Request,
    record: SessionRecord,
    bucket: str,
    limit: int,
    window: float = _RATE_10MIN,
) -> None:
    ip = _client_ip(request)
    if not _limiter.allow(f"{bucket}:sid:{record.sid}", limit, window):
        raise _too_many()
    # Session rotation must not reset the budget: also bound the client IP.
    if not _limiter.allow(f"{bucket}:ip:{ip}", limit, window):
        raise _too_many()


def _rotate_for_first_trip(
    record: SessionRecord, request: Request, response: Response
) -> SessionRecord:
    """New session id when the browser claims its first trip (fixation defence)."""
    if record.trips:
        return record
    fresh = _sessions.rotate(record)
    set_session_cookie(response, request, fresh)
    request.state.trip_session = fresh
    return fresh


def _owned(trip_id: str, record: SessionRecord) -> Trip:
    if not valid_trip_id(trip_id):
        raise _not_found()
    trip = get_store().get_owned(trip_id, record.sid)
    if trip is None:
        raise _not_found()
    return trip


def _safe_web_link(link: str | None) -> str | None:
    """Validate the QR link; it is encoded into the PDF, never fetched."""
    if not link:
        return None
    value = link.strip()
    if len(value) > 2000:
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    if parts.username or parts.password:
        return None
    return value


@router.get("/api/trips/status")
def trips_status() -> dict[str, Any]:
    return {
        "ok": True,
        "providers": provider_status(),
        "security": {
            "auth": "signed-http-only-session",
            "csrf": f"{CSRF_HEADER} header for POST/PATCH/DELETE",
            "scope": "trips are readable only by the session that created them",
            "note": (
                "Local demo: one host, file-backed session registry. "
                "Multi-host deployments must use shared storage and revoke sessions server-side."
            ),
        },
    }


@router.get("/api/trips/session")
def trip_session(record: SessionRecord = Depends(require_session)) -> dict[str, Any]:
    """Bootstrap endpoint: returns the per-session CSRF token (never the secret)."""
    return {
        "csrf": record.csrf,
        "expiresAt": record.expires_at,
        "trips": record.trips,
    }


@router.delete("/api/trips/session")
def end_trip_session(
    request: Request,
    response: Response,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    _sessions.revoke(record.sid)
    clear_session_cookie(response, request)
    return {"ok": True}


@router.post("/api/trips/plan")
def plan_trip(
    body: PlanRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    _enforce(request, record, "plan", config.TRIP_PLAN_PER_10MIN)
    existing = _owned(body.tripId, record) if body.tripId else None
    if existing is None:
        record = _rotate_for_first_trip(record, request, response)
    if not _plan_gate.acquire():
        raise _too_many(15)
    try:
        agent = get_agent()
        try:
            trip = agent.plan(
                body.message,
                hotel=body.hotel,
                trip_id=existing.id if existing else None,
            )
        except ProviderError as exc:
            raise _http_from_provider(exc) from exc
        store = get_store()
        if not store.set_owner(trip.id, record.sid):
            raise HTTPException(
                status_code=409,
                detail={"code": "trip_conflict", "message": "Не удалось сохранить поездку"},
            )
        if existing is None:
            record = _sessions.mark_trip(record)
        return {"trip": trip.model_dump()}
    finally:
        _plan_gate.release()


@router.post("/api/trips/plan/stream")
def plan_trip_stream(
    body: PlanRequest,
    request: Request,
    response: Response,
    record: SessionRecord = Depends(require_session),
) -> StreamingResponse:
    _enforce(request, record, "plan", config.TRIP_PLAN_PER_10MIN)
    existing = _owned(body.tripId, record) if body.tripId else None
    if existing is None:
        record = _rotate_for_first_trip(record, request, response)
    if not _plan_gate.acquire():
        raise _too_many(15)

    agent = get_agent()

    def gen():
        try:
            for event in agent.plan_stream(
                body.message,
                hotel=body.hotel,
                trip_id=existing.id if existing else None,
            ):
                if event.get("type") == "done":
                    trip = Trip.model_validate(event["trip"])
                    if get_store().set_owner(trip.id, record.sid) and existing is None:
                        _sessions.mark_trip(record)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            _plan_gate.release()

    stream = StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    set_session_cookie(stream, request, record)
    return stream


@router.post("/api/trips/{trip_id}/chat")
def chat_trip(
    trip_id: str,
    body: ChatRequest,
    request: Request,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    _enforce(request, record, "chat", config.TRIP_CHAT_PER_10MIN)
    _owned(trip_id, record)
    if not _plan_gate.acquire():
        raise _too_many(15)
    try:
        agent = get_agent()
        try:
            trip = agent.chat(trip_id, body.message)
        except ProviderError as exc:
            raise _http_from_provider(exc) from exc
        return {"trip": trip.model_dump()}
    finally:
        _plan_gate.release()


@router.get("/api/trips/{trip_id}")
def get_trip(
    trip_id: str,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    return {"trip": _owned(trip_id, record).model_dump()}


@router.patch("/api/trips/{trip_id}")
def patch_trip(
    trip_id: str,
    body: TripPatch,
    request: Request,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    _enforce(request, record, "chat", config.TRIP_CHAT_PER_10MIN)
    trip = _owned(trip_id, record)
    data = trip.model_dump()
    updates = body.model_dump(exclude_unset=True)
    for key in ("summary", "days", "hotel", "intent"):
        if key in updates:
            data[key] = updates[key]
    try:
        updated = Trip.model_validate(data)
    except ValueError as exc:  # pragma: no cover - bounded by TripPatch already
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_trip", "message": "Некорректные данные поездки"},
        ) from exc
    get_store().save(updated)
    return {"trip": updated.model_dump()}


@router.delete("/api/trips/{trip_id}")
def delete_trip(
    trip_id: str,
    request: Request,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    _enforce(request, record, "chat", config.TRIP_CHAT_PER_10MIN)
    if not get_store().delete_owned(trip_id, record.sid):
        raise _not_found()
    return {"ok": True}


@router.post("/api/trips/{trip_id}/rebuild-day")
def rebuild_day(
    trip_id: str,
    body: RebuildDayRequest,
    request: Request,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    _enforce(request, record, "chat", config.TRIP_CHAT_PER_10MIN)
    _owned(trip_id, record)
    msg = body.message or f"Перестрой день {body.dayNumber}"
    if not _plan_gate.acquire():
        raise _too_many(15)
    try:
        agent = get_agent()
        try:
            trip = agent.chat(trip_id, msg)
        except ProviderError as exc:
            raise _http_from_provider(exc) from exc
        return {"trip": trip.model_dump()}
    finally:
        _plan_gate.release()


@router.get("/api/trips/{trip_id}/pdf")
def trip_pdf(
    trip_id: str,
    request: Request,
    record: SessionRecord = Depends(require_session),
    link: str | None = Query(default=None),
) -> Response:
    _enforce(request, record, "pdf", config.TRIP_PDF_PER_10MIN)
    trip = _owned(trip_id, record)
    if not _pdf_gate.acquire():
        raise _too_many(10)
    try:
        pdf_bytes = build_trip_pdf(trip, web_link=_safe_web_link(link))
    finally:
        _pdf_gate.release()
    response = Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="oh-route-{trip_id}.pdf"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
    set_session_cookie(response, request, record)
    return response


@router.post("/api/places/search")
def places_search(
    body: PlacesSearchRequest,
    request: Request,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    _enforce(request, record, "geo", config.TRIP_GEO_PER_MINUTE, _RATE_1MIN)
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
def routes_calculate(
    body: RouteCalculateRequest,
    request: Request,
    record: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    _enforce(request, record, "geo", config.TRIP_GEO_PER_MINUTE, _RATE_1MIN)
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
