"""Security regression tests for the public trip API.

Covers per-session trip isolation, CSRF, expiry/revocation, fixation,
parameter bounds, rate limiting and PDF ownership.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.trip_planner import api as trip_api
from services.trip_planner import config as trip_config
from services.trip_planner.agent import TripPlannerAgent
from services.trip_planner.models import TRIP_ID_PATTERN
from services.trip_planner.providers.fixtures import (
    FixtureGeocodingProvider,
    FixturePlacesProvider,
    FixtureRoutingProvider,
)
from services.trip_planner.session import (
    COOKIE_NAME,
    SessionStore,
    decode_cookie,
    encode_cookie,
)
from services.trip_planner.store import TripStore

MESSAGE = "Казань на 1 день, главные достопримечательности"
CSRF_HEADER = "X-CSRF-Token"


class _DisabledGiga:
    available = False
    client = None

    def extract_intent(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


@pytest.fixture(autouse=True)
def _offline_media(monkeypatch: pytest.MonkeyPatch) -> None:
    # The security suite must not depend on Wikimedia/GigaChat network calls.
    monkeypatch.setattr(
        "services.trip_planner.photos.enrich_places", lambda places, **_kw: places
    )
    monkeypatch.setattr(
        "services.trip_planner.photos.enrich_trip_photos", lambda trip, **_kw: trip
    )


@pytest.fixture()
def store(tmp_path: Path) -> TripStore:
    return TripStore(tmp_path / "trips")


@pytest.fixture()
def sessions(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.json")


@pytest.fixture()
def app(store: TripStore, sessions: SessionStore) -> FastAPI:
    agent = TripPlannerAgent(
        geocoding=FixtureGeocodingProvider(),
        places=FixturePlacesProvider(),
        routing=FixtureRoutingProvider(),
        store=store,
        gigachat=_DisabledGiga(),  # type: ignore[arg-type]
    )
    application = FastAPI()
    application.include_router(trip_api.router)
    trip_api.set_agent(agent)
    trip_api.set_session_store(sessions)
    trip_api.get_limiter().reset()
    yield application
    trip_api.get_limiter().reset()


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _csrf(client: TestClient) -> str:
    res = client.get("/api/trips/session")
    assert res.status_code == 200
    data = res.json()
    assert "sid" not in data
    return data["csrf"]


def _plan(client: TestClient, message: str = MESSAGE) -> dict:
    token = _csrf(client)
    res = client.post(
        "/api/trips/plan",
        json={"message": message},
        headers={CSRF_HEADER: token},
    )
    assert res.status_code == 200, res.text
    return res.json()["trip"]


def _headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: _csrf(client)}


def test_session_cookie_is_http_only_and_same_site(client: TestClient) -> None:
    res = client.get("/api/trips/session")
    cookie = res.headers.get("set-cookie", "")
    assert COOKIE_NAME in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie.replace("samesite=lax", "SameSite=lax")
    assert "Path=/api" in cookie
    # Local http demo must keep working: Secure is only forced behind HTTPS.
    assert "Secure" not in cookie
    assert "csrf" in res.json()


def test_csrf_required_for_writes(client: TestClient) -> None:
    _csrf(client)
    res = client.post("/api/trips/plan", json={"message": MESSAGE})
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "csrf_failed"

    res = client.post(
        "/api/trips/plan",
        json={"message": MESSAGE},
        headers={CSRF_HEADER: "forged"},
    )
    assert res.status_code == 403

    res = client.post(
        "/api/trips/plan",
        json={"message": MESSAGE},
        headers={CSRF_HEADER: "forged", "Origin": "https://evil.example"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "csrf_failed"


def test_cross_site_origin_cannot_write_even_with_token(client: TestClient) -> None:
    token = _csrf(client)
    res = client.post(
        "/api/trips/plan",
        json={"message": MESSAGE},
        headers={CSRF_HEADER: token, "Origin": "https://evil.example"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "origin_rejected"


def test_two_sessions_cannot_read_update_or_delete_each_other(app: FastAPI) -> None:
    alice, bob = TestClient(app), TestClient(app)
    trip = _plan(alice)
    trip_id = trip["id"]
    assert trip_id.startswith("trip_")

    # Bob cannot read, chat, rebuild, patch, download or delete.
    assert bob.get(f"/api/trips/{trip_id}").status_code == 404
    assert bob.post(
        f"/api/trips/{trip_id}/chat",
        json={"message": "Убери музей"},
        headers=_headers(bob),
    ).status_code == 404
    assert bob.post(
        f"/api/trips/{trip_id}/rebuild-day",
        json={"dayNumber": 1},
        headers=_headers(bob),
    ).status_code == 404
    assert bob.patch(
        f"/api/trips/{trip_id}",
        json={"summary": "pwned"},
        headers=_headers(bob),
    ).status_code == 404
    assert bob.get(f"/api/trips/{trip_id}/pdf").status_code == 404
    assert bob.delete(f"/api/trips/{trip_id}", headers=_headers(bob)).status_code == 404

    # Alice still sees the untouched trip.
    res = alice.get(f"/api/trips/{trip_id}")
    assert res.status_code == 200
    assert res.json()["trip"]["summary"] != "pwned"


def test_foreign_trip_id_cannot_be_overwritten_via_plan(app: FastAPI) -> None:
    alice, bob = TestClient(app), TestClient(app)
    trip = _plan(alice)
    before = alice.get(f"/api/trips/{trip['id']}").json()["trip"]

    res = bob.post(
        "/api/trips/plan",
        json={"message": "Стамбул на 3 дня", "tripId": trip["id"]},
        headers=_headers(bob),
    )
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "trip_not_found"

    after = alice.get(f"/api/trips/{trip['id']}").json()["trip"]
    assert after["destination"] == before["destination"]
    assert after["id"] == before["id"]


@pytest.mark.parametrize("trip_id", ["not-a-trip", "trip_short", "../etc/passwd", "trip_" + "z" * 32])
def test_malformed_trip_ids_are_not_found(client: TestClient, trip_id: str) -> None:
    assert client.get(f"/api/trips/{trip_id}").status_code == 404
    assert client.delete(f"/api/trips/{trip_id}", headers=_headers(client)).status_code == 404


def test_generated_trip_ids_match_strict_uuid4_shape(client: TestClient) -> None:
    import re

    trip_id = _plan(client)["id"]
    assert re.fullmatch(TRIP_ID_PATTERN, trip_id)
    assert decode_cookie(client.cookies.get(COOKIE_NAME))


def test_session_revocation_invalidates_old_cookie(app: FastAPI) -> None:
    client = TestClient(app)
    trip = _plan(client)
    old_cookie = client.cookies.get(COOKIE_NAME)
    assert old_cookie

    res = client.delete("/api/trips/session", headers=_headers(client))
    assert res.status_code == 200
    # Replay the revoked cookie as an attacker would.
    client.cookies.set(COOKIE_NAME, old_cookie, path="/api")
    assert client.get(f"/api/trips/{trip['id']}").status_code == 404


def test_expired_session_cannot_read_trip(app: FastAPI, sessions: SessionStore) -> None:
    client = TestClient(app)
    trip = _plan(client)
    sid = decode_cookie(client.cookies.get(COOKIE_NAME))
    assert sid
    data = sessions._read()
    data[sid]["expires_at"] = int(time.time()) - 5
    sessions._write(data)

    # The cookie signature is still valid, but the server-side record expired.
    assert client.get(f"/api/trips/{trip['id']}").status_code == 404


def test_session_rotation_and_forged_cookie_cannot_hijack(app: FastAPI) -> None:
    victim = TestClient(app)
    first_value = _cookie_value(victim.get("/api/trips/session").headers["set-cookie"])
    old_sid = decode_cookie(first_value)
    trip = _plan(victim)
    new_value = victim.cookies.get(COOKIE_NAME)
    assert old_sid and new_value and new_value != first_value

    # Old (pre-rotation) session id is revoked.
    attacker = TestClient(app)
    attacker.cookies.set(COOKIE_NAME, first_value, path="/api")
    assert attacker.get(f"/api/trips/{trip['id']}").status_code == 404

    # An unsigned/tampered id is never accepted.
    forged = "v1." + _b64('{"sid":"attacker","exp":9999999999}') + ".deadbeef"
    attacker.cookies.set(COOKIE_NAME, forged, path="/api")
    assert attacker.get(f"/api/trips/{trip['id']}").status_code == 404


def _cookie_value(set_cookie: str) -> str:
    return set_cookie.split(";", 1)[0].split("=", 1)[1]


def _b64(value: str) -> str:
    import base64

    return base64.urlsafe_b64encode(value.encode()).rstrip(b"=").decode()


def test_expiry_is_enforced_in_signed_payload(sessions: SessionStore) -> None:
    record = sessions.create()
    token = encode_cookie(record)
    assert decode_cookie(token) == record.sid
    expired = encode_cookie(
        type(record)(
            sid=record.sid,
            csrf=record.csrf,
            created_at=record.created_at,
            expires_at=int(time.time()) - 1,
            trips=0,
        )
    )
    assert decode_cookie(expired) is None
    assert decode_cookie(token[:-3] + "abc") is None


def test_patch_is_bounded(client: TestClient) -> None:
    trip = _plan(client)
    headers = _headers(client)

    too_many_days = [
        {
            "dayNumber": index + 1,
            "stops": [],
            "segments": [],
            "route": {"distanceMeters": 0, "durationSeconds": 0},
        }
        for index in range(8)
    ]
    res = client.patch(
        f"/api/trips/{trip['id']}", json={"days": too_many_days}, headers=headers
    )
    assert res.status_code == 422

    huge_summary = "x" * 5000
    res = client.patch(
        f"/api/trips/{trip['id']}", json={"summary": huge_summary}, headers=headers
    )
    assert res.status_code == 422

    res = client.patch(
        f"/api/trips/{trip['id']}", json={"summary": "Короткое описание"}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["trip"]["summary"] == "Короткое описание"


def test_plan_rate_limit_returns_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(trip_config, "TRIP_PLAN_PER_10MIN", 1)
    _plan(client)
    res = client.post(
        "/api/trips/plan",
        json={"message": MESSAGE},
        headers=_headers(client),
    )
    assert res.status_code == 429
    assert res.headers.get("retry-after")


def test_pdf_saved_for_owner_and_foreign_denied(app: FastAPI, store: TripStore) -> None:
    client = TestClient(app)
    trip = _plan(client)
    res = client.get(
        f"/api/trips/{trip['id']}/pdf",
        params={"link": "https://example.com/oh-route?trip=" + trip["id"]},
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/pdf")
    assert res.content[:4] == b"%PDF"
    assert len(res.content) > 500
    assert "no-store" in res.headers.get("cache-control", "")

    # A dangerous QR link is dropped rather than embedded.
    res = client.get(
        f"/api/trips/{trip['id']}/pdf", params={"link": "javascript:alert(1)"}
    )
    assert res.status_code == 200
    assert res.content[:4] == b"%PDF"

    # Ownership sidecar never leaks into API output.
    raw = json.loads((store.root / f"{trip['id']}.json").read_text(encoding="utf-8"))
    assert "owner" not in raw and "sid" not in raw
    assert (store.root / ".owners" / f"{trip['id']}.owner").exists()


def test_streaming_endpoint_requires_session_and_csrf(app: FastAPI) -> None:
    client = TestClient(app)
    res = client.post("/api/trips/plan/stream", json={"message": MESSAGE})
    assert res.status_code == 403

    token = _csrf(client)
    res = client.post(
        "/api/trips/plan/stream",
        json={"message": MESSAGE},
        headers={CSRF_HEADER: token},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    assert COOKIE_NAME in res.headers.get("set-cookie", "")
