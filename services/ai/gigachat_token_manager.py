from __future__ import annotations

import threading
import time
import uuid
from typing import Any

import httpx

from . import gigachat_config as cfg
from .gigachat_types import GigaChatError, TokenState


class GigaChatTokenManager:
    """In-memory access token with single-flight refresh and 60s early expiry."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        auth_key: str | None = None,
        scope: str | None = None,
        auth_url: str | None = None,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self._auth_key = auth_key if auth_key is not None else cfg.GIGACHAT_AUTH_KEY
        self._scope = scope or cfg.GIGACHAT_SCOPE
        self._auth_url = auth_url or cfg.GIGACHAT_AUTH_URL
        self._state: TokenState | None = None
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            verify: bool | str = True
            if cfg.GIGACHAT_TLS_INSECURE:
                verify = False
            elif cfg.GIGACHAT_CA_BUNDLE:
                verify = cfg.GIGACHAT_CA_BUNDLE
            self._client = httpx.Client(timeout=cfg.GIGACHAT_TIMEOUT, verify=verify)
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def invalidate(self) -> None:
        with self._lock:
            self._state = None

    def get_token(self, force: bool = False) -> str:
        if not self._auth_key:
            raise GigaChatError("auth_missing", "GIGACHAT_AUTH_KEY is not configured")

        if force:
            self.invalidate()

        now = time.monotonic()
        with self._lock:
            if self._state and self._state.expires_at - 60 > now:
                return self._state.access_token

        # Single-flight refresh: parallel callers share one OAuth request
        with self._refresh_lock:
            now = time.monotonic()
            with self._lock:
                if self._state and self._state.expires_at - 60 > now:
                    return self._state.access_token

            token, expires_in = self._fetch_token()
            expires_at = time.monotonic() + max(30, expires_in)
            with self._lock:
                self._state = TokenState(access_token=token, expires_at=expires_at)
            return token

    def _fetch_token(self) -> tuple[str, float]:
        client = self._ensure_client()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self._auth_key}",
        }
        try:
            resp = client.post(
                self._auth_url,
                headers=headers,
                data={"scope": self._scope},
            )
        except httpx.TimeoutException as exc:
            raise GigaChatError("timeout", "OAuth request timed out") from exc
        except httpx.HTTPError as exc:
            raise GigaChatError("network", f"OAuth network error: {type(exc).__name__}") from exc

        if resp.status_code == 401:
            raise GigaChatError("unauthorized", "OAuth rejected Authorization key", status=401)
        if resp.status_code == 403:
            body = _safe_body(resp)
            hint = ""
            low = body.lower()
            if "b2b" in low or "corp" in low or "business" in low:
                hint = " Scope may need GIGACHAT_API_B2B or GIGACHAT_API_CORP — do not guess; check project type."
            raise GigaChatError("forbidden", f"OAuth forbidden.{hint}", status=403)
        if resp.status_code >= 500 or resp.status_code == 429:
            raise GigaChatError("transient", f"OAuth transient HTTP {resp.status_code}", status=resp.status_code)
        if resp.status_code >= 400:
            raise GigaChatError(
                "oauth_failed",
                f"OAuth failed HTTP {resp.status_code}",
                status=resp.status_code,
            )

        data: dict[str, Any] = resp.json()
        token = data.get("access_token")
        if not token:
            raise GigaChatError("oauth_failed", "OAuth response missing access_token")
        expires_in = float(data.get("expires_at") or data.get("expires_in") or 1800)
        # Some APIs return absolute ms timestamp in expires_at
        if expires_in > 10_000_000:
            expires_in = max(30.0, (expires_in / 1000.0) - time.time())
        return str(token), float(expires_in)


def _safe_body(resp: httpx.Response) -> str:
    try:
        text = resp.text
    except Exception:  # noqa: BLE001
        return ""
    # Never leak Authorization-like material
    return text[:400]
