"""Signed, server-revocable demo sessions for the trip API.

The public demo has no accounts: a trip belongs to the browser session that
created it.  The browser gets an opaque HttpOnly cookie holding a signed
session id; the server keeps a small registry so sessions can expire and be
revoked (a signature alone cannot be revoked).

Design notes
------------
* Cookies are signed with HMAC-SHA256 using ``TRIP_SESSION_SECRET``.  When the
  variable is unset (local demo) a random secret is generated once per machine
  in ``data/trip_session_secret`` (mode 0600, gitignored).  No secret ever
  reaches the frontend.
* The session id is generated server-side only: a client-supplied id is
  ignored, which prevents session fixation.
* CSRF protection is a per-session token returned by ``GET
  /api/trips/session`` and required in ``X-CSRF-Token`` for unsafe methods.
* ``Secure`` is enabled automatically for HTTPS requests (or explicitly with
  ``TRIP_COOKIE_SECURE=1``) while local ``http://127.0.0.1`` demos keep
  working.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import config

COOKIE_NAME = "oh_trip_session"
CSRF_HEADER = "x-csrf-token"
COOKIE_PATH = "/api"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_MAX_REGISTRY_ENTRIES = 20_000


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _secret_path() -> Path:
    return config.TRIP_SESSION_SECRET_FILE


def _load_secret() -> bytes:
    env = (os.getenv("TRIP_SESSION_SECRET") or "").strip()
    if env:
        return env.encode("utf-8")
    path = _secret_path()
    try:
        return path.read_bytes().strip()
    except OSError:
        pass
    secret = secrets.token_hex(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(secret)
    except OSError:
        # Read-only checkouts still work; sessions simply do not survive a restart.
        pass
    return secret.encode("utf-8")


_SECRET: bytes | None = None
_SECRET_LOCK = threading.Lock()


def _secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        with _SECRET_LOCK:
            if _SECRET is None:
                _SECRET = _load_secret()
    return _SECRET


def reset_secret_cache() -> None:
    """Test hook: force re-reading the signing secret."""
    global _SECRET
    with _SECRET_LOCK:
        _SECRET = None


@dataclass(frozen=True)
class SessionRecord:
    sid: str
    csrf: str
    created_at: int
    expires_at: int
    trips: int = 0

    @property
    def expired(self) -> bool:
        return self.expires_at <= int(time.time())

    def as_dict(self) -> dict[str, int | str]:
        return {
            "sid": self.sid,
            "csrf": self.csrf,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "trips": self.trips,
        }


def _sign(payload: str) -> str:
    digest = hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def encode_cookie(record: SessionRecord) -> str:
    payload = _b64encode(
        json.dumps({"sid": record.sid, "exp": record.expires_at}, separators=(",", ":")).encode()
    )
    return f"v1.{payload}.{_sign(payload)}"


def decode_cookie(token: str | None) -> str | None:
    """Return the session id from a valid signed cookie, else ``None``."""
    if not token or not token.startswith("v1."):
        return None
    try:
        _version, payload, signature = token.split(".", 2)
    except ValueError:
        return None
    if not payload or not signature:
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    try:
        data = json.loads(_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    sid = data.get("sid")
    exp = data.get("exp")
    if not isinstance(sid, str) or len(sid) < 16 or not isinstance(exp, int):
        return None
    if exp <= int(time.time()):
        return None
    return sid


class SessionStore:
    """Tiny JSON registry shared by processes on the same machine.

    Good enough for the documented single-host demo.  A multi-host deployment
    must move this to Redis (and keep the same signed-cookie contract).
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config.TRIP_SESSION_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: dict[str, dict] | None = None

    def _read(self) -> dict[str, dict]:
        if self._cache is not None:
            return self._cache
        data: dict[str, dict] = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for sid, value in raw.items():
                    if isinstance(sid, str) and isinstance(value, dict):
                        data[sid] = value
        except (OSError, json.JSONDecodeError):
            data = {}
        self._cache = data
        return data

    def _write(self, data: dict[str, dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass
        self._cache = data

    def _purge(self, data: dict[str, dict], now: int) -> None:
        for sid, entry in list(data.items()):
            try:
                if int(entry.get("expires_at", 0)) <= now:
                    data.pop(sid, None)
            except (TypeError, ValueError):
                data.pop(sid, None)
        while len(data) > _MAX_REGISTRY_ENTRIES:
            data.pop(next(iter(data)))

    def create(self) -> SessionRecord:
        now = int(time.time())
        record = SessionRecord(
            sid=secrets.token_urlsafe(32),
            csrf=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + config.TRIP_SESSION_TTL_SECONDS,
        )
        with self._lock:
            data = self._read()
            self._purge(data, now)
            data[record.sid] = record.as_dict()
            self._write(data)
        return record

    def resolve(self, token: str | None) -> SessionRecord | None:
        sid = decode_cookie(token)
        if not sid:
            return None
        with self._lock:
            entry = self._read().get(sid)
            if not isinstance(entry, dict):
                return None
            try:
                record = SessionRecord(
                    sid=sid,
                    csrf=str(entry["csrf"]),
                    created_at=int(entry["created_at"]),
                    expires_at=int(entry["expires_at"]),
                    trips=int(entry.get("trips", 0)),
                )
            except (KeyError, TypeError, ValueError):
                return None
            if record.expired:
                self._read().pop(sid, None)
                self._write(self._read())
                return None
            return record

    def rotate(self, record: SessionRecord) -> SessionRecord:
        """Invalidate the old id and issue a fresh one (fixation defence).

        The CSRF token is preserved so an in-flight client (which already
        fetched it) is not forced to re-bootstrap mid-flow.
        """
        fresh = self.create()
        rotated = SessionRecord(
            sid=fresh.sid,
            csrf=record.csrf,
            created_at=fresh.created_at,
            expires_at=fresh.expires_at,
            trips=record.trips,
        )
        with self._lock:
            data = self._read()
            data.pop(record.sid, None)
            data[rotated.sid] = rotated.as_dict()
            self._write(data)
        return rotated

    def mark_trip(self, record: SessionRecord) -> SessionRecord:
        with self._lock:
            data = self._read()
            entry = data.get(record.sid)
            if not isinstance(entry, dict):
                return record
            entry["trips"] = int(entry.get("trips", 0)) + 1
            data[record.sid] = entry
            self._write(data)
            return SessionRecord(
                sid=record.sid,
                csrf=record.csrf,
                created_at=record.created_at,
                expires_at=record.expires_at,
                trips=int(entry["trips"]),
            )

    def revoke(self, sid: str) -> None:
        with self._lock:
            data = self._read()
            if data.pop(sid, None) is not None:
                self._write(data)


def cookie_secure(request) -> bool:  # noqa: ANN001 - Starlette Request without import cycle
    if config.TRIP_COOKIE_SECURE:
        return True
    return request.url.scheme == "https"


def set_session_cookie(response, request, record: SessionRecord) -> None:  # noqa: ANN001
    response.set_cookie(
        COOKIE_NAME,
        encode_cookie(record),
        max_age=max(0, record.expires_at - int(time.time())),
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
        path=COOKIE_PATH,
    )


def clear_session_cookie(response, request) -> None:  # noqa: ANN001
    response.delete_cookie(
        COOKIE_NAME,
        path=COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
    )
