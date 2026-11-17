"""Write-auth, demo-mode guards, CSRF-safe demo sessions, enrich rate limiting.

Public clients must NOT gain write privileges via X-Demo-Mutation alone.
Writes require either:
  - matching X-Write-Token (server-side secret, never shipped as VITE_*), or
  - a short-lived HttpOnly demo session cookie issued only on loopback when
    DEMO_MODE is on (HMAC-signed with WRITE_TOKEN; CSRF Origin/Referer check).

Frontend must never embed HOTEL_INTELLIGENCE_WRITE_TOKEN.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from fastapi import Header, HTTPException, Request, Response

from . import config

DEMO_SESSION_COOKIE = "hi_demo_session"
DEMO_SESSION_TTL_SEC = 8 * 3600
_CSRF_SAFE_ORIGINS = frozenset(
    {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    }
)


class EnrichRateLimiter:
    """Process-local sliding-window counter for enrich calls."""

    def __init__(self, max_per_min: int | None = None) -> None:
        self.max_per_min = (
            max_per_min
            if max_per_min is not None
            else config.HOTEL_INTELLIGENCE_ENRICH_MAX_PER_MIN
        )
        self._timestamps: list[float] = []
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._timestamps.clear()

    def check(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._timestamps = [t for t in self._timestamps if now - t < 60.0]
            if len(self._timestamps) >= self.max_per_min:
                raise HTTPException(
                    status_code=429,
                    detail="enrich_rate_limit_exceeded",
                )
            self._timestamps.append(now)


_enrich_limiter = EnrichRateLimiter()


def get_enrich_limiter() -> EnrichRateLimiter:
    return _enrich_limiter


def reset_enrich_limiter(max_per_min: int | None = None) -> EnrichRateLimiter:
    """Test helper: reset and optionally retarget the limit."""
    global _enrich_limiter
    _enrich_limiter = EnrichRateLimiter(max_per_min=max_per_min)
    return _enrich_limiter


def _client_is_loopback(request: Request) -> bool:
    """True only for the *direct* TCP peer. Never trust X-Forwarded-For here.

    A reverse proxy that forwards public traffic would present as the proxy host
    (not loopback) unless the app is bound only to localhost. Spoofed
    X-Forwarded-For: 127.0.0.1 must NOT grant demo sessions.
    """
    # Explicitly ignore forwarded headers for privilege decisions.
    _ = request.headers.get("x-forwarded-for")
    _ = request.headers.get("x-real-ip")
    host = (request.client.host if request.client else "") or ""
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _sign_session(payload: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def mint_demo_session_value(*, secret: str, ttl: int = DEMO_SESSION_TTL_SEC) -> str:
    exp = int(time.time()) + ttl
    payload = f"demo|{exp}"
    return f"{payload}|{_sign_session(payload, secret)}"


def verify_demo_session_value(raw: str | None, *, secret: str) -> bool:
    if not raw or not secret:
        return False
    parts = raw.split("|")
    if len(parts) != 3:
        return False
    kind, exp_s, sig = parts
    if kind != "demo":
        return False
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    payload = f"{kind}|{exp_s}"
    expected = _sign_session(payload, secret)
    return hmac.compare_digest(expected, sig)


def _origin_ok(request: Request) -> bool:
    """CSRF defense for cookie-authenticated writes."""
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin and origin in _CSRF_SAFE_ORIGINS:
        return True
    referer = (request.headers.get("referer") or "").strip()
    if referer:
        try:
            parsed = urlparse(referer)
            ref_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            if ref_origin in _CSRF_SAFE_ORIGINS:
                return True
        except Exception:  # noqa: BLE001
            pass
    # TestClient / same-origin server tools often omit Origin
    if _client_is_loopback(request) and not origin and not referer:
        return True
    return False


def issue_demo_session(request: Request, response: Response) -> dict[str, Any]:
    """POST /demo/session — loopback + DEMO_MODE only; sets HttpOnly cookie.

    Production / public deploy: keep DEMO_MODE=0 so this endpoint stays 403.
    Demo sessions never escalate to non-simulated hotelier authority.
    """
    if not config.DEMO_MODE:
        raise HTTPException(status_code=403, detail="demo_mode_disabled")
    if not _client_is_loopback(request):
        raise HTTPException(status_code=403, detail="demo_session_loopback_only")
    # Reject if a proxy claims a public client even when peer is loopback
    # (misconfigured local proxy bridging the internet).
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff and xff not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(
            status_code=403,
            detail="demo_session_forbidden_behind_public_proxy",
        )
    secret = (config.HOTEL_INTELLIGENCE_WRITE_TOKEN or "").strip()
    if not secret:
        raise HTTPException(
            status_code=401,
            detail="write_token_not_configured_set_HOTEL_INTELLIGENCE_WRITE_TOKEN",
        )
    value = mint_demo_session_value(secret=secret)
    response.set_cookie(
        key=DEMO_SESSION_COOKIE,
        value=value,
        httponly=True,
        samesite="strict",
        secure=False,  # local http://127.0.0.1 demos
        max_age=DEMO_SESSION_TTL_SEC,
        path="/api/hotel-intelligence",
    )
    return {
        "ok": True,
        "mode": "demo_session",
        "simulated_only": True,
        "ttl_sec": DEMO_SESSION_TTL_SEC,
        "httponly": True,
        "note": "Cookie grants local demo writes only; hotelier answers stay simulated.",
    }


def require_write_auth(
    request: Request,
    *,
    x_write_token: str | None = Header(default=None, alias="X-Write-Token"),
    x_demo_mutation: str | None = Header(default=None, alias="X-Demo-Mutation"),
) -> dict[str, Any]:
    """Authorize mutating hotel-intelligence endpoints.

    Rules:
    1. WRITE_TOKEN must be configured (fail closed).
    2. Matching X-Write-Token authorizes (server/scripts/tests).
    3. Valid demo session cookie + loopback + DEMO_MODE + CSRF Origin check.
    4. X-Demo-Mutation alone is NEVER enough.
    """
    token = (x_write_token or "").strip()
    expected = (config.HOTEL_INTELLIGENCE_WRITE_TOKEN or "").strip()
    demo_hdr = (x_demo_mutation or "").strip()
    loopback = _client_is_loopback(request)

    if not expected:
        raise HTTPException(
            status_code=401,
            detail="write_token_not_configured_set_HOTEL_INTELLIGENCE_WRITE_TOKEN",
        )

    if token == expected:
        return {
            "mode": "token",
            "force_simulated": bool(config.DEMO_MODE),
            "loopback": loopback,
        }

    cookie = request.cookies.get(DEMO_SESSION_COOKIE)
    if (
        config.DEMO_MODE
        and loopback
        and verify_demo_session_value(cookie, secret=expected)
    ):
        if not _origin_ok(request):
            raise HTTPException(status_code=403, detail="csrf_origin_rejected")
        return {
            "mode": "demo_session",
            "force_simulated": True,
            "loopback": True,
        }

    if demo_hdr == "1":
        raise HTTPException(
            status_code=403,
            detail="demo_mutation_header_alone_insufficient_use_write_token_or_demo_session",
        )

    raise HTTPException(status_code=401, detail="write_auth_required")


def enforce_hotelier_simulated(
    *,
    simulated: bool,
    auth: dict[str, Any],
) -> bool:
    """In demo mode always force simulated; reject simulated=false with 403."""
    if config.DEMO_MODE or auth.get("force_simulated"):
        if not simulated:
            raise HTTPException(
                status_code=403,
                detail="simulated_false_forbidden_in_demo_mode",
            )
        return True
    return simulated


def resolve_bootstrap_demo_dir(client_demo_dir: str | None) -> None:
    """Forbid arbitrary demo_dir from clients (always use config.DEMO_DIR)."""
    if client_demo_dir is not None and str(client_demo_dir).strip():
        raise HTTPException(
            status_code=400,
            detail="demo_dir_query_forbidden_use_server_config",
        )
