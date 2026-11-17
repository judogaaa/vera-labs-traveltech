"""Extract structured claims from free-text hotelier answers.

Deterministic regex/rules first. Optional GigaChat only if available and
explicitly enabled — always mark extraction method. Simulated answers use
source kind hotelier_simulated and must never alone set status verified
(enforced by AttributeObservation validators).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

ExtractionMethod = Literal["regex_rules", "gigachat", "none"]


@dataclass
class ExtractedClaim:
    attribute_key: str
    value: Any
    scope_kind: Literal["hotel", "building", "facade", "room_type", "room"] = "hotel"
    scope_identifier: str | None = None
    confidence: float = 0.55
    evidence_span: str | None = None


@dataclass
class ExtractionResult:
    claims: list[ExtractedClaim] = field(default_factory=list)
    method: ExtractionMethod = "none"
    method_detail: str = ""
    raw_text: str = ""


_BLACKOUT_YES = re.compile(
    r"(?i)("
    r"\bblackout\b|\bблэкаут\b|\bблекаут\b|"
    r"плотн\w*\s+штор|"
    r"затемн[её]н\w*\s+штор|"
    r"darkening\s+curtain|"
    r"есть\s+(плотн\w+\s+)?штор|"
    r"шторы?\s+(есть|стоят|установл)"
    r")"
)
_BLACKOUT_NO = re.compile(
    r"(?i)("
    r"нет\s+(blackout|блэкаут|блекаут|плотн\w*\s+штор)|"
    r"(blackout|блэкаут|блекаут)[\w\-]*\s*штор\w*\s+нет|"
    r"(blackout|блэкаут|блекаут)\s+нет|"
    r"нет\s*,?\s*(blackout|блэкаут|блекаут)|"
    r"штор\w*\s+нет|"
    r"без\s+(blackout|блэкаут|плотных\s+штор)|"
    r"не\s+предусмотр|"
    r"только\s+обычн\w*\s+штор|"
    r"\bno\s+blackout\b|"
    r"\bblackout\s+нет\b"
    r")"
)
_COURTYARD = re.compile(
    r"(?i)\b(двор|courtyard|внутренн\w*\s+двор|во\s+двор)\b"
)
_ROOM_TYPE = re.compile(
    r"(?i)\b("
    r"standard|deluxe|suite|superior|family|"
    r"стандарт|делюкс|сьют|семейн\w*"
    r")\b"
)
_ROOM_NUM = re.compile(
    r"(?i)\b(?:номер\w*|room)\s*(?:№\s*)?([A-Za-z]?\d{2,4})\b"
)


def extract_claims(
    raw_text: str,
    *,
    attribute_hints: list[str] | None = None,
    allow_gigachat: bool = False,
) -> ExtractionResult:
    text = (raw_text or "").strip()
    if not text:
        return ExtractionResult(method="none", method_detail="empty_text", raw_text=text)

    claims = _regex_extract(text, attribute_hints=attribute_hints or [])
    if claims:
        return ExtractionResult(
            claims=claims,
            method="regex_rules",
            method_detail="deterministic_patterns_v1",
            raw_text=text,
        )

    if allow_gigachat:
        llm = _try_gigachat(text, attribute_hints=attribute_hints or [])
        if llm is not None:
            return llm

    return ExtractionResult(
        claims=[],
        method="none",
        method_detail="no_confident_pattern",
        raw_text=text,
    )


def _normalize_room_type(raw: str) -> str:
    low = raw.lower()
    mapping = {
        "deluxe": "Deluxe",
        "делюкс": "Deluxe",
        "standard": "Standard",
        "стандарт": "Standard",
        "suite": "Suite",
        "сьют": "Suite",
        "superior": "Superior",
        "family": "Family",
        "семейный": "Family",
        "семейные": "Family",
        "семейных": "Family",
    }
    for k, v in mapping.items():
        if low.startswith(k) or k in low:
            return v
    return raw.capitalize()


def _clause_scope(
    clause: str,
) -> tuple[Literal["hotel", "building", "facade", "room_type", "room"], str | None]:
    room_m = _ROOM_NUM.search(clause)
    if room_m:
        return "room", room_m.group(1)
    # Ranges like 301-305
    range_m = re.search(r"(?i)\b(?:номер\w*|room)?\s*([A-Za-z]?\d{2,4})\s*[-–—]\s*([A-Za-z]?\d{2,4})\b", clause)
    if range_m:
        return "room", f"{range_m.group(1)}-{range_m.group(2)}"
    rt = _ROOM_TYPE.search(clause)
    if rt:
        return "room_type", _normalize_room_type(rt.group(1))
    return "hotel", None


def _regex_extract(text: str, *, attribute_hints: list[str]) -> list[ExtractedClaim]:
    """Split multi-sentence answers into per-scope claims (Standard vs Deluxe)."""
    claims: list[ExtractedClaim] = []
    hints = set(attribute_hints) or {
        "blackout_curtains",
        "courtyard_rooms",
    }

    # Split on sentence/clause boundaries so "Standard нет. Deluxe есть." → 2 claims
    clauses = [
        c.strip()
        for c in re.split(r"[.!?;]|(?:\n+)|(?:\s+[—–-]\s+)", text)
        if c and c.strip()
    ]
    if not clauses:
        clauses = [text]

    want_blackout = (
        "blackout_curtains" in hints
        or "blackout" in text.lower()
        or "штор" in text.lower()
        or "блэкаут" in text.lower()
        or "блекаут" in text.lower()
    )

    if want_blackout:
        for clause in clauses:
            if not re.search(r"(?i)штор|blackout|блэкаут|блекаут|затемн", clause):
                # Still allow short clauses that only name the room type after a prior mention
                if not _ROOM_TYPE.search(clause) and not _ROOM_NUM.search(clause):
                    continue
                if not re.search(r"(?i)нет|есть|обычн|blackout|штор", clause):
                    continue
            scope_kind, scope_id = _clause_scope(clause)
            no_m = _BLACKOUT_NO.search(clause)
            yes_m = _BLACKOUT_YES.search(clause)
            # Prefer explicit no over yes when both fire in same clause
            if no_m and (
                not yes_m
                or (no_m.start() < yes_m.start())
                or re.search(r"(?i)нет|без|не\s+предусмотр|только\s+обычн", clause)
            ):
                # "шторы обычные" without blackout word → no
                claims.append(
                    ExtractedClaim(
                        attribute_key="blackout_curtains",
                        value=False,
                        scope_kind=scope_kind,
                        scope_identifier=scope_id,
                        confidence=0.6,
                        evidence_span=no_m.group(0),
                    )
                )
            elif yes_m:
                claims.append(
                    ExtractedClaim(
                        attribute_key="blackout_curtains",
                        value=True,
                        scope_kind=scope_kind,
                        scope_identifier=scope_id,
                        confidence=0.62,
                        evidence_span=yes_m.group(0),
                    )
                )
            elif re.search(r"(?i)шторы?\s+обычн|обычн\w*\s+штор", clause):
                claims.append(
                    ExtractedClaim(
                        attribute_key="blackout_curtains",
                        value=False,
                        scope_kind=scope_kind,
                        scope_identifier=scope_id,
                        confidence=0.58,
                        evidence_span="обычные шторы",
                    )
                )

    if "courtyard_rooms" in hints or _COURTYARD.search(text):
        m = _COURTYARD.search(text)
        if m and re.search(r"(?i)\b(есть|доступн|предлага|yes|available)\b", text):
            scope_kind, scope_id = _clause_scope(text)
            claims.append(
                ExtractedClaim(
                    attribute_key="courtyard_rooms",
                    value=True,
                    scope_kind=scope_kind,
                    scope_identifier=scope_id,
                    confidence=0.55,
                    evidence_span=m.group(0),
                )
            )

    # Deduplicate identical scope+value
    seen: set[tuple[Any, ...]] = set()
    unique: list[ExtractedClaim] = []
    for c in claims:
        key = (c.attribute_key, c.value, c.scope_kind, c.scope_identifier)
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


def _try_gigachat(text: str, *, attribute_hints: list[str]) -> ExtractionResult | None:
    """Best-effort optional LLM assist — never invents if call fails."""
    try:
        from services.hotel_intelligence.gigachat_nlu import extract_hotelier_claims_llm
    except Exception:  # noqa: BLE001
        return None
    llm = extract_hotelier_claims_llm(text, attribute_hints=attribute_hints)
    if llm is None or not llm.claims:
        return None
    claims: list[ExtractedClaim] = []
    for c in llm.claims:
        claims.append(
            ExtractedClaim(
                attribute_key=c.attribute_key,
                value=c.value,
                scope_kind=c.scope_kind,
                scope_identifier=c.scope_identifier,
                confidence=float(c.confidence),
                evidence_span=c.evidence_span,
            )
        )
    detail = "gigachat_structured"
    if llm.contradictions:
        detail += f";contradictions={len(llm.contradictions)}"
    return ExtractionResult(
        claims=claims,
        method="gigachat",
        method_detail=detail,
        raw_text=text,
    )


def simulate_hotelier_answer(attribute_key: str, *, affirmative: bool = True) -> str:
    """Demo-only free-text answers. Caller must mark source hotelier_simulated."""
    if attribute_key == "blackout_curtains":
        if affirmative:
            return (
                "В номерах категории Deluxe установлены плотные шторы блэкаут; "
                "в Standard — обычные затемняющие."
            )
        return "К сожалению, blackout-штор в Standard нет, только обычные шторы."
    if attribute_key == "courtyard_rooms":
        return "Есть несколько номеров во внутренний двор, тише чем на улицу."
    return "Уточните, пожалуйста, какой тип номера вас интересует."
