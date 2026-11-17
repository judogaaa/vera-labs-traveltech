"""GigaChat NLU helpers for О!Подбор — extract, hotelier claims, explanations.

Never invents coordinates, hotel facts, or routes. All structured output is
validated with Pydantic; failures fall back to deterministic parsers.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

ALLOWED_ATTRIBUTE_KEYS = frozenset(
    {
        "walk_to_metro",
        "walk_to_metro_entrance_min",
        "walk_to_metro_min",
        "external_noise_risk",
        "blackout_curtains",
        "courtyard_rooms",
        "late_night_pharmacy_walk",
        "family_infrastructure",
        "family_friendly_nearby",
        "parking_nearby",
        "car_access",
        "car_access_street",
        "night_services",
        "night_services_nearby",
    }
)

# Map LLM/synonym keys onto registry keys used by calculators/store.
ATTRIBUTE_KEY_ALIASES: dict[str, str] = {
    "walk_to_metro_min": "walk_to_metro",
    "walk_to_metro_entrance_min": "walk_to_metro",
    "family_friendly_nearby": "family_infrastructure",
    "parking_nearby": "car_access",
    "car_access_street": "car_access",
    "night_services_nearby": "night_services",
}


REGISTRY_ATTRIBUTE_KEYS = frozenset(
    {
        "walk_to_metro",
        "external_noise_risk",
        "blackout_curtains",
        "courtyard_rooms",
        "late_night_pharmacy_walk",
        "family_infrastructure",
        "car_access",
        "night_services",
    }
)


def normalize_attribute_key(key: str) -> str:
    k = (key or "").strip()
    return ATTRIBUTE_KEY_ALIASES.get(k, k)


class WishConstraint(BaseModel):
    key: str
    role: Literal["must", "should"] = "should"
    constraint: dict[str, Any] = Field(default_factory=dict)

    @field_validator("key")
    @classmethod
    def key_allowed(cls, v: str) -> str:
        key = normalize_attribute_key(v)
        if key not in REGISTRY_ATTRIBUTE_KEYS:
            raise ValueError(f"attribute_not_in_allowlist:{v}")
        return key


class HotelWishExtract(BaseModel):
    city: str | None = None
    room_type: str | None = None
    wishes: list[WishConstraint] = Field(default_factory=list)
    negations: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
    clarifying_question: str | None = None
    notes: str | None = None


class HotelierClaimLLM(BaseModel):
    attribute_key: str
    value: Any
    scope_kind: Literal["hotel", "building", "facade", "room_type", "room"] = "hotel"
    scope_identifier: str | None = None
    confidence: float = Field(default=0.55, ge=0.0, le=1.0)
    evidence_span: str | None = None

    @field_validator("attribute_key")
    @classmethod
    def key_allowed(cls, v: str) -> str:
        key = normalize_attribute_key(v)
        if key not in REGISTRY_ATTRIBUTE_KEYS:
            raise ValueError(f"attribute_not_in_allowlist:{v}")
        return key


class HotelierExtractLLM(BaseModel):
    claims: list[HotelierClaimLLM] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


def _client():
    from services.ai.gigachat_client import get_gigachat_client

    return get_gigachat_client()


def extract_hotel_wishes(
    query: str,
    *,
    previous_query: str | None = None,
    conversation: list[dict[str, str]] | None = None,
    known_keys: list[str] | None = None,
) -> HotelWishExtract | None:
    """Structured wish extract. Returns None if GigaChat unavailable/fails."""
    client = _client()
    if client is None:
        return None
    keys = sorted(set(known_keys or []) | set(ALLOWED_ATTRIBUTE_KEYS))
    context_bits: list[str] = []
    if previous_query:
        context_bits.append(f"Предыдущий запрос: {previous_query}")
    if conversation:
        for turn in conversation[-6:]:
            role = turn.get("role") or "user"
            content = (turn.get("content") or "").strip()
            if content:
                context_bits.append(f"{role}: {content}")
    context_block = "\n".join(context_bits) if context_bits else "(нет)"

    system = (
        "Ты — NLU-модуль подбора отелей Vera Labs. "
        "Извлеки структурированные пожелания путешественника. "
        "Не выдумывай отели, координаты и факты. "
        f"Разрешённые attribute_key только из: {keys}. "
        "role=must для жёстких требований, should для предпочтений. "
        "Для walk_to_metro_entrance_min / walk_to_metro_min укажи constraint.max_minutes. "
        "Для external_noise_risk при «без клубов» добавь reject_nightclub=true. "
        "Негации и уточнения относительно предыдущего запроса должны отразиться в wishes. "
        "Если нельзя проверить по доступным атрибутам — положь в unsupported и/или clarifying_question."
    )
    prompt = (
        f"Контекст диалога:\n{context_block}\n\n"
        f"Текущий запрос пользователя:\n{query}\n\n"
        "Верни JSON со схемой: "
        '{"city":str|null,"room_type":str|null,'
        '"wishes":[{"key":str,"role":"must"|"should","constraint":{}}],'
        '"negations":[str],"unsupported":[str],'
        '"clarifying_question":str|null,"notes":str|null}'
    )
    try:
        raw = client.structured_json(prompt, system=system, repair_attempts=1)
        parsed = HotelWishExtract.model_validate(raw)
        # Drop invalid wishes silently (validator already filters keys)
        return parsed
    except (ValidationError, Exception) as exc:  # noqa: BLE001
        logger.info("gigachat_wish_extract_failed: %s", type(exc).__name__)
        return None


def extract_hotelier_claims_llm(
    text: str,
    *,
    attribute_hints: list[str] | None = None,
) -> HotelierExtractLLM | None:
    client = _client()
    if client is None:
        return None
    hints = attribute_hints or ["blackout_curtains", "courtyard_rooms"]
    system = (
        "Извлеки утверждения отельера об атрибутах отеля. "
        "Учитывай отрицания («нет», «без»). "
        "Разделяй типы номеров (Standard/Deluxe) и диапазоны номеров. "
        "Не выдумывай факты вне текста. "
        f"Разрешённые attribute_key: {sorted(ALLOWED_ATTRIBUTE_KEYS)}. "
        f"Приоритетные подсказки: {hints}."
    )
    prompt = (
        f"Текст отельера:\n{text}\n\n"
        "JSON: {\"claims\":[{\"attribute_key\":str,\"value\":any,"
        "\"scope_kind\":\"hotel\"|\"room_type\"|\"room\",\"scope_identifier\":str|null,"
        "\"confidence\":0-1,\"evidence_span\":str}],\"contradictions\":[str]}"
    )
    try:
        raw = client.structured_json(prompt, system=system, repair_attempts=1)
        return HotelierExtractLLM.model_validate(raw)
    except (ValidationError, Exception) as exc:  # noqa: BLE001
        logger.info("gigachat_hotelier_extract_failed: %s", type(exc).__name__)
        return None


def explain_from_evidence(
    *,
    hotel_name: str,
    query: str,
    matched: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
    unknown: list[dict[str, Any]],
) -> str | None:
    """Plain-language explanation that must not invent new attribute values."""
    client = _client()
    if client is None:
        return None
    system = (
        "Объясни рекомендацию отеля простым русским языком. "
        "Используй ТОЛЬКО переданные matched/unmatched/unknown. "
        "Не добавляй факты, расстояния и характеристики, которых нет во входе. "
        "Если unknown — честно скажи, что не подтверждено."
    )
    prompt = (
        f"Запрос: {query}\nОтель: {hotel_name}\n"
        f"matched={matched}\nunmatched={unmatched}\nunknown={unknown}\n"
        "Верни JSON {\"explanation\": \"...\"}"
    )
    try:
        raw = client.structured_json(prompt, system=system, repair_attempts=0)
        text = raw.get("explanation") if isinstance(raw, dict) else None
        return str(text).strip() if text else None
    except Exception as exc:  # noqa: BLE001
        logger.info("gigachat_explain_failed: %s", type(exc).__name__)
        return None


def describe_image_features(
    *,
    image_bytes: bytes | None = None,
    image_b64: str | None = None,
    image_url: str | None = None,
    crop_hint: str | None = None,
    declared_mime: str | None = None,
    filename: str | None = None,
) -> dict[str, Any] | None:
    """GigaChat Vision assist via POST /v1/files + chat attachments.

    Never embeds truncated base64 in a text prompt. Never fetches remote URLs
    (SSRF). Identity matching remains ResNet/CLIP/Qdrant — this only describes
    visual features. ``vision_invoked`` is True only when an image file id was
    attached to the chat request.
    """
    import base64
    import json
    import re

    from services.ai.gigachat_types import GigaChatError
    from services.hotel_intelligence.vision_image import (
        proof_safe_meta,
        reject_remote_image_url,
        validate_image_bytes,
    )

    try:
        reject_remote_image_url(image_url)
    except ValueError as exc:
        return {
            "features": [],
            "refined_query": None,
            "confidence": 0,
            "limitation": str(exc),
            "model_invoked": False,
            "vision_invoked": False,
            "unsupported": True,
        }

    raw_bytes = image_bytes
    if raw_bytes is None and image_b64:
        try:
            raw_bytes = base64.b64decode(image_b64, validate=False)
        except Exception:  # noqa: BLE001
            return {
                "features": [],
                "refined_query": None,
                "confidence": 0,
                "limitation": "invalid_base64",
                "model_invoked": False,
                "vision_invoked": False,
                "unsupported": True,
            }
    if not raw_bytes:
        return None

    try:
        validated = validate_image_bytes(
            raw_bytes, declared_mime=declared_mime, filename=filename
        )
    except ValueError as exc:
        return {
            "features": [],
            "refined_query": None,
            "confidence": 0,
            "limitation": str(exc),
            "model_invoked": False,
            "vision_invoked": False,
            "unsupported": True,
        }

    client = _client()
    if client is None:
        return {
            "features": [],
            "refined_query": None,
            "confidence": 0,
            "limitation": "gigachat_not_configured",
            "model_invoked": False,
            "vision_invoked": False,
            "unsupported": True,
        }

    system = (
        "Ты — ассистент визуального поиска отелей Vera Labs. "
        "Изображение приложено как файл (attachments). "
        "Опиши только видимые признаки: фасад, материалы, вывеска, стиль, окружение. "
        "Не называй конкретный бренд/отель без явной читаемой вывески. "
        "Не подменяй компьютерное зрение — только описание и уточняющий текстовый запрос. "
        "Ответь ТОЛЬКО JSON: "
        '{"features":[str],"refined_query":str,"confidence":0-1,"limitation":str|null}'
    )
    hint = crop_hint or "полный кадр"
    prompt = (
        f"Область кадра: {hint}. "
        "Опиши визуальные особенности для уточнения поиска похожих отелей."
    )

    try:
        result, upload_meta = client.chat_with_image(
            prompt,
            image_bytes=validated.data,
            filename=validated.filename,
            content_type=validated.mime,
            system=system,
            temperature=0.1,
        )
    except GigaChatError as exc:
        # Honest: Vision unsupported / model cannot process images / upload failed
        unsupported = exc.status in {400, 422} or "vision" in (exc.message or "").lower()
        return {
            "features": [],
            "refined_query": None,
            "confidence": 0,
            "limitation": f"vision_api_error:{exc.code}:{exc.status}",
            "model_invoked": False,
            "vision_invoked": False,
            "unsupported": unsupported or True,
            "proof": proof_safe_meta(
                model=None,
                file_id=None,
                bytes_len=len(validated.data),
                mime=validated.mime,
                width=validated.width,
                height=validated.height,
                vision_used=False,
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "features": [],
            "refined_query": None,
            "confidence": 0,
            "limitation": f"vision_unavailable:{type(exc).__name__}",
            "model_invoked": False,
            "vision_invoked": False,
            "unsupported": True,
        }

    content = (result.content or "").strip()
    parsed: dict[str, Any] | None = None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                parsed = None
    if not isinstance(parsed, dict):
        # Model saw the image but did not return JSON — still Vision was used.
        features = [t.strip() for t in re.split(r"[,;\n]", content) if t.strip()][:8]
        parsed = {
            "features": features,
            "refined_query": content[:160] if content else None,
            "confidence": 0.4,
            "limitation": "non_json_vision_response",
        }

    file_id = str(upload_meta.get("file_id") or "")
    vision_ok = bool(file_id)
    return {
        "features": list(parsed.get("features") or [])[:12],
        "refined_query": parsed.get("refined_query"),
        "confidence": parsed.get("confidence"),
        "limitation": parsed.get("limitation") or "assistive_only_not_identity",
        # model_invoked alone is NOT proof of Vision — use vision_invoked
        "model_invoked": vision_ok,
        "vision_invoked": vision_ok,
        "unsupported": False,
        "model": result.model,
        "proof": proof_safe_meta(
            model=result.model,
            file_id=file_id,
            bytes_len=len(validated.data),
            mime=validated.mime,
            width=validated.width,
            height=validated.height,
            vision_used=vision_ok,
            content_preview=content,
        ),
    }
