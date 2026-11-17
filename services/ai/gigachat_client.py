from __future__ import annotations

import json
import logging
import random
import time
import uuid
from typing import Any, Iterator

import httpx

from . import gigachat_config as cfg
from .gigachat_token_manager import GigaChatTokenManager
from .gigachat_types import (
    ChatMessage,
    ChatResult,
    FunctionDef,
    GigaChatError,
    ObservabilityEvent,
)

log = logging.getLogger("services.ai.gigachat")

# Prefer stronger models when available on the account
MODEL_PREFERENCE = [
    "GigaChat-2-Pro",
    "GigaChat-2-Max",
    "GigaChat-Pro",
    "GigaChat-Max",
    "GigaChat-2",
    "GigaChat",
]


class GigaChatClient:
    def __init__(
        self,
        token_manager: GigaChatTokenManager | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        cfg.require_enabled_credentials()
        verify: bool | str = True
        if cfg.GIGACHAT_TLS_INSECURE:
            log.warning("GIGACHAT_TLS_INSECURE enabled — diagnostic only, not for production")
            verify = False
        elif cfg.GIGACHAT_CA_BUNDLE:
            verify = cfg.GIGACHAT_CA_BUNDLE
        self._http = httpx.Client(timeout=cfg.GIGACHAT_TIMEOUT, verify=verify)
        self._tokens = token_manager or GigaChatTokenManager(client=self._http)
        self.base_url = (base_url or cfg.GIGACHAT_BASE_URL).rstrip("/")
        self._model = model if model is not None else cfg.GIGACHAT_MODEL
        self._events: list[ObservabilityEvent] = []

    @property
    def available(self) -> bool:
        return bool(cfg.GIGACHAT_ENABLED and cfg.GIGACHAT_AUTH_KEY)

    @property
    def model(self) -> str:
        return self._model or "GigaChat"

    def close(self) -> None:
        self._tokens.close()
        self._http.close()

    def pop_events(self) -> list[ObservabilityEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def _record(self, event: ObservabilityEvent) -> None:
        self._events.append(event)
        log.info(
            "gigachat %s status=%s latency_ms=%.0f model=%s corr=%s err=%s",
            event.kind,
            event.status,
            event.latency_ms,
            event.model,
            event.correlation_id,
            event.error_code,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        accept_retry_401: bool = True,
        correlation_id: str | None = None,
    ) -> httpx.Response:
        corr = correlation_id or str(uuid.uuid4())
        url = f"{self.base_url}{path}"
        attempts = 0
        last_exc: Exception | None = None
        while attempts < cfg.GIGACHAT_MAX_RETRIES:
            attempts += 1
            token = self._tokens.get_token(force=False)
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "X-Request-ID": corr,
            }
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            t0 = time.perf_counter()
            try:
                resp = self._http.request(method, url, headers=headers, json=json_body)
            except httpx.TimeoutException as exc:
                last_exc = exc
                self._backoff(attempts)
                continue
            except httpx.HTTPError as exc:
                last_exc = exc
                self._backoff(attempts)
                continue

            latency = (time.perf_counter() - t0) * 1000
            if resp.status_code == 401 and accept_retry_401:
                self._tokens.invalidate()
                try:
                    token = self._tokens.get_token(force=True)
                except GigaChatError:
                    self._record(
                        ObservabilityEvent(
                            kind="http",
                            latency_ms=latency,
                            status=401,
                            correlation_id=corr,
                            error_code="unauthorized",
                        )
                    )
                    raise GigaChatError("unauthorized", "Token refresh failed after 401", status=401)
                headers["Authorization"] = f"Bearer {token}"
                t1 = time.perf_counter()
                resp = self._http.request(method, url, headers=headers, json=json_body)
                latency = (time.perf_counter() - t1) * 1000
                if resp.status_code == 401:
                    self._record(
                        ObservabilityEvent(
                            kind="http",
                            latency_ms=latency,
                            status=401,
                            correlation_id=corr,
                            error_code="unauthorized",
                        )
                    )
                    raise GigaChatError("unauthorized", "Still unauthorized after token refresh", status=401)

            if resp.status_code in {429, 500, 502, 503, 504}:
                self._record(
                    ObservabilityEvent(
                        kind="http",
                        latency_ms=latency,
                        status=resp.status_code,
                        correlation_id=corr,
                        error_code="transient",
                    )
                )
                self._backoff(attempts)
                continue

            if resp.status_code >= 400:
                self._record(
                    ObservabilityEvent(
                        kind="http",
                        latency_ms=latency,
                        status=resp.status_code,
                        correlation_id=corr,
                        error_code="http_error",
                    )
                )
                raise GigaChatError(
                    "http_error",
                    f"GigaChat HTTP {resp.status_code}",
                    status=resp.status_code,
                )

            self._record(
                ObservabilityEvent(
                    kind="http",
                    latency_ms=latency,
                    status=resp.status_code,
                    correlation_id=corr,
                    model=self._model or None,
                )
            )
            return resp

        raise GigaChatError(
            "transient",
            f"GigaChat request failed after retries: {type(last_exc).__name__ if last_exc else 'unknown'}",
        )

    def _backoff(self, attempt: int) -> None:
        delay = min(8.0, (2 ** (attempt - 1)) * 0.4) + random.uniform(0, 0.25)
        time.sleep(delay)

    def list_models(self) -> list[str]:
        resp = self._request("GET", "/v1/models")
        data = resp.json()
        ids: list[str] = []
        for item in data.get("data") or []:
            mid = item.get("id")
            if mid:
                ids.append(str(mid))
        return ids

    def select_best_model(self, available: list[str] | None = None) -> str:
        ids = available if available is not None else self.list_models()
        if self._model and self._model in ids:
            return self._model
        for pref in MODEL_PREFERENCE:
            for mid in ids:
                if mid == pref or mid.startswith(pref):
                    self._model = mid
                    return mid
        if ids:
            self._model = ids[0]
            return ids[0]
        self._model = self._model or "GigaChat"
        return self._model

    def ensure_model(self) -> str:
        if self._model:
            return self._model
        return self.select_best_model()

    def chat(
        self,
        messages: list[ChatMessage] | list[dict[str, Any]],
        *,
        functions: list[FunctionDef] | list[dict[str, Any]] | None = None,
        function_call: str | dict[str, str] | None = "auto",
        functions_state_id: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        stream: bool = False,
        correlation_id: str | None = None,
    ) -> ChatResult:
        model = self.ensure_model()
        api_messages: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, ChatMessage):
                api_messages.append(m.to_api())
            else:
                api_messages.append(m)

        body: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "temperature": temperature,
        }
        if stream:
            body["stream"] = True
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        # GigaChat: top-level `functions` only on the initial tool turn.
        # Follow-ups use functions_state_id + assistant/function history (no functions array).
        if functions:
            body["function_call"] = function_call if function_call is not None else "auto"
            body["functions"] = [
                f.to_api() if isinstance(f, FunctionDef) else f for f in functions
            ]
        if functions_state_id:
            body["functions_state_id"] = functions_state_id

        t0 = time.perf_counter()
        resp = self._request("POST", "/v1/chat/completions", json_body=body, correlation_id=correlation_id)
        latency = (time.perf_counter() - t0) * 1000
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        result = ChatResult(
            content=message.get("content"),
            function_call=message.get("function_call"),
            functions_state_id=message.get("functions_state_id") or data.get("functions_state_id"),
            model=data.get("model") or model,
            finish_reason=choice.get("finish_reason"),
            latency_ms=latency,
            status=resp.status_code,
            raw=data,
        )
        self._record(
            ObservabilityEvent(
                kind="chat",
                latency_ms=latency,
                status=resp.status_code,
                model=result.model,
                correlation_id=correlation_id,
            )
        )
        return result

    def complete_text(self, prompt: str, *, system: str | None = None) -> ChatResult:
        msgs: list[ChatMessage] = []
        if system:
            msgs.append(ChatMessage(role="system", content=system))
        msgs.append(ChatMessage(role="user", content=prompt))
        return self.chat(msgs, function_call="none", functions=None)

    def upload_file(
        self,
        data: bytes,
        *,
        filename: str = "image.jpg",
        content_type: str = "image/jpeg",
        purpose: str = "general",
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Upload bytes to GigaChat file store (POST /v1/files). Returns file metadata incl. id."""
        corr = correlation_id or str(uuid.uuid4())
        url = f"{self.base_url}/v1/files"
        token = self._tokens.get_token(force=False)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "X-Request-ID": corr,
            "X-Session-ID": corr,
        }
        files = {
            "file": (filename, data, content_type),
        }
        form = {"purpose": purpose}
        t0 = time.perf_counter()
        try:
            resp = self._http.post(url, headers=headers, files=files, data=form)
        except Exception as exc:  # noqa: BLE001
            raise GigaChatError("upload_failed", f"file upload error: {type(exc).__name__}") from exc
        latency = (time.perf_counter() - t0) * 1000
        if resp.status_code == 401:
            token = self._tokens.get_token(force=True)
            headers["Authorization"] = f"Bearer {token}"
            resp = self._http.post(url, headers=headers, files=files, data=form)
            latency = (time.perf_counter() - t0) * 1000
        if resp.status_code >= 400:
            self._record(
                ObservabilityEvent(
                    kind="upload",
                    latency_ms=latency,
                    status=resp.status_code,
                    correlation_id=corr,
                    error_code="upload_http_error",
                    model=self._model or None,
                )
            )
            raise GigaChatError(
                "upload_http_error",
                f"GigaChat file upload HTTP {resp.status_code}",
                status=resp.status_code,
            )
        meta = resp.json()
        self._record(
            ObservabilityEvent(
                kind="upload",
                latency_ms=latency,
                status=resp.status_code,
                correlation_id=corr,
                model=self._model or None,
            )
        )
        return meta if isinstance(meta, dict) else {"raw": meta}

    def chat_with_image(
        self,
        prompt: str,
        *,
        image_bytes: bytes,
        filename: str = "image.jpg",
        content_type: str = "image/jpeg",
        system: str | None = None,
        temperature: float = 0.2,
        correlation_id: str | None = None,
    ) -> tuple[ChatResult, dict[str, Any]]:
        """Upload image then chat with attachments=[file_id]. Never embeds raw base64 in prompt."""
        meta = self.upload_file(
            image_bytes,
            filename=filename,
            content_type=content_type,
            purpose="general",
            correlation_id=correlation_id,
        )
        file_id = str(meta.get("id") or meta.get("file_id") or "").strip()
        if not file_id:
            raise GigaChatError("upload_missing_id", "GigaChat file upload returned no id")
        msgs: list[ChatMessage] = []
        if system:
            msgs.append(ChatMessage(role="system", content=system))
        msgs.append(
            ChatMessage(
                role="user",
                content=prompt,
                attachments=[file_id],
            )
        )
        result = self.chat(msgs, function_call="none", correlation_id=correlation_id, temperature=temperature)
        return result, {"file_id": file_id, "upload": {"id": file_id, "bytes": len(image_bytes), "content_type": content_type}}

    def structured_json(
        self,
        prompt: str,
        *,
        system: str,
        repair_attempts: int = 1,
    ) -> dict[str, Any]:
        """Ask for JSON; validate parse with up to repair_attempts bounded repairs."""
        messages = [
            ChatMessage(role="system", content=system + "\nОтветь только валидным JSON-объектом."),
            ChatMessage(role="user", content=prompt),
        ]
        result = self.chat(messages, function_call="none")
        parsed = _extract_json(result.content or "")
        if parsed is not None:
            return parsed
        for _ in range(max(0, repair_attempts)):
            messages.append(ChatMessage(role="assistant", content=result.content or ""))
            messages.append(
                ChatMessage(
                    role="user",
                    content="Предыдущий ответ невалидный JSON. Верни только исправленный JSON-объект.",
                )
            )
            result = self.chat(messages, function_call="none")
            parsed = _extract_json(result.content or "")
            if parsed is not None:
                return parsed
        raise GigaChatError("structured_failed", "Could not parse structured JSON from model")

    def run_tool_loop(
        self,
        messages: list[ChatMessage],
        functions: list[FunctionDef],
        executor: Any,
        *,
        max_rounds: int = 8,
        correlation_id: str | None = None,
    ) -> tuple[ChatResult, list[dict[str, Any]]]:
        """Execute GigaChat function-calling loop. executor(name, args_dict) -> dict/str."""
        history = list(messages)
        tool_trace: list[dict[str, Any]] = []
        state_id: str | None = None
        started = False

        for _ in range(max_rounds):
            if not started:
                result = self.chat(
                    history,
                    functions=functions,
                    function_call="auto",
                    correlation_id=correlation_id,
                )
                started = True
            else:
                # Follow-up: no top-level functions array (GigaChat 422 otherwise).
                # Keep assistant/function turns; pass functions_state_id.
                follow = [m for m in history if getattr(m, "role", None) != "system"]
                result = self.chat(
                    follow,
                    functions=None,
                    function_call=None,
                    functions_state_id=state_id,
                    correlation_id=correlation_id,
                )
            if result.functions_state_id:
                state_id = result.functions_state_id

            if not result.function_call:
                return result, tool_trace

            fc = result.function_call
            name = str(fc.get("name") or "")
            raw_args = fc.get("arguments") or "{}"
            if isinstance(raw_args, dict):
                args = raw_args
            else:
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    args = {}

            assistant_msg = ChatMessage(
                role="assistant",
                content=result.content or "",
                function_call=fc,
                functions_state_id=state_id,
            )
            history.append(assistant_msg)

            try:
                out = executor(name, args)
            except Exception as exc:  # noqa: BLE001
                out = {"error": type(exc).__name__, "message": str(exc)[:300]}

            tool_trace.append({"name": name, "args_keys": list(args.keys()), "ok": "error" not in out})
            content = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
            # External tool content is untrusted data, not instructions
            history.append(
                ChatMessage(
                    role="function",
                    name=name,
                    content=content[:12000],
                )
            )

        raise GigaChatError("tool_loop_limit", f"Exceeded {max_rounds} function-call rounds")


def _extract_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


_CLIENT: GigaChatClient | None = None


def get_gigachat_client() -> GigaChatClient | None:
    global _CLIENT
    if not cfg.GIGACHAT_ENABLED or not cfg.GIGACHAT_AUTH_KEY:
        return None
    if _CLIENT is None:
        _CLIENT = GigaChatClient()
    return _CLIENT
