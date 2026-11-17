from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class GigaChatError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass
class TokenState:
    access_token: str
    expires_at: float  # monotonic deadline


@dataclass
class ChatMessage:
    role: str
    content: str | None = None
    name: str | None = None
    function_call: dict[str, Any] | None = None
    functions_state_id: str | None = None
    # GigaChat Vision: file ids from POST /v1/files (one image per message).
    attachments: list[str] | None = None

    def to_api(self) -> dict[str, Any]:
        out: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            out["content"] = self.content
        if self.name:
            out["name"] = self.name
        if self.function_call is not None:
            out["function_call"] = self.function_call
        if self.functions_state_id:
            out["functions_state_id"] = self.functions_state_id
        if self.attachments:
            out["attachments"] = list(self.attachments)
        return out


@dataclass
class FunctionDef:
    name: str
    description: str
    parameters: dict[str, Any]
    return_parameters: dict[str, Any] | None = None

    def to_api(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
        if self.return_parameters:
            out["return_parameters"] = self.return_parameters
        return out


@dataclass
class ChatResult:
    content: str | None
    function_call: dict[str, Any] | None
    functions_state_id: str | None
    model: str
    finish_reason: str | None
    latency_ms: float
    status: int
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ObservabilityEvent:
    kind: str
    latency_ms: float
    status: int | None = None
    model: str | None = None
    correlation_id: str | None = None
    error_code: str | None = None
    # Never include prompts, tokens, or auth keys
