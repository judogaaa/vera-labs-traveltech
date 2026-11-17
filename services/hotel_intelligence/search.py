"""Natural-language hotel search over stored observations.

unknown != match. Ranking prefers verified/estimated matches; unexplained
requirements stay in unmatched/unknown buckets.

Intent patterns come from AttributeDefinition.intent_patterns (registry),
not a hardcoded list in this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from .attributes.definitions import build_default_registry
from .evidence import resolve_observations
from .matchers import match_constraint
from .models import AttributeObservation, ClaimStatus
from .registry import AttributeDefinition, AttributeRegistry
from .store import IntelligenceStore

_WALK_MAX_MIN = re.compile(r"(?i)(\d+)\s*(?:мин|минут|min)")
_ROOM_TYPE = re.compile(
    r"(?i)\b(deluxe|standard|suite|superior|семейный|стандарт|делюкс)\b"
)
_NEG_CLUB = re.compile(
    r"(?i)(?:не\s+возле\s+клуб|без\s+клуб|не\s+рядом\s+с\s+клуб|"
    r"not\s+near\s+(?:night)?clubs?|away\s+from\s+(?:night)?clubs?)"
)
_POS_CLUB_STREET = re.compile(
    r"(?i)(?:клубн\w*\s+улиц|рядом\s+(?:с\s+)?(?:ночн\w*\s+)?клуб|"
    r"возле\s+(?:ночн\w*\s+)?клуб|near\s+(?:night)?clubs?|"
    r"nightlife\s+street)"
)
_BLACKOUT_NEG = re.compile(
    r"(?i)(?:"
    r"без\s+(?:blackout|блэкаут|блекаут|плотных\s+штор)|"
    r"(?:blackout|блэкаут|блекаут)\s+нет|"
    r"нет\s+(?:blackout|блэкаут|блекаут|плотных\s+штор)|"
    r"не\s+(?:нуж|хочу|хотим)\w*\s+(?:blackout|блэкаут|плотных\s+штор)"
    r")"
)
_FAMILY_ROOM = re.compile(r"(?i)семейн\w*\s+номер|family\s+room|номер\w*\s+для\s+семьи")
_CITY = re.compile(
    r"(?i)\b("
    r"istanbul|стамбул\w*|"
    r"kazan|казан\w*|"
    r"moscow|москв\w*|"
    r"sochi|сочи|"
    r"antalya|анталь\w*|"
    r"dubai|дуба\w*|"
    r"prague|праг\w*"
    r")\b"
)
_FLOOR_MIN = re.compile(r"(?i)(?:после|выше|от)\s+(?:пятого|5|пятого\s+этажа)|(?:floor|этаж)\s*[>≥]?\s*(\d+)")
_UNSUPPORTED_INTENTS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"(?i)вид\s+на\s+закат|закат|sunset\s+view|west(?:ern)?\s+view"),
        "sunset_view",
        "Building facade / sunset orientation is not in the attribute registry",
    ),
    (
        re.compile(
            r"(?i)(?:после|выше)\s+(?:пятого|5)|"
            r"пятого\s+этажа|"
            r"этаж(?:е|а)?\s*(?:выше|от)\s*5|"
            r"floor\s*[>≥]\s*5|"
            r"после\s+пятого"
        ),
        "min_floor",
        "Floor number / room elevation is not confirmed in demo observations",
    ),
]


@dataclass
class RequestedAttribute:
    key: str
    role: Literal["must", "should"]
    constraint: dict[str, Any] = field(default_factory=dict)
    definition: AttributeDefinition | None = None


@dataclass
class ParsedQuery:
    requested: list[RequestedAttribute]
    city: str | None = None
    room_type: str | None = None
    unsupported: list[dict[str, str]] = field(default_factory=list)
    extraction: Literal["deterministic", "gigachat"] = "deterministic"


@dataclass
class HotelMatchExplanation:
    hotel_id: str
    name: str | None
    score: float
    matched: list[dict[str, Any]]
    unmatched: list[dict[str, Any]]
    unknown: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]


def _normalize_room_type(raw: str | None) -> str | None:
    if not raw:
        return None
    low = raw.lower()
    if "делюкс" in low or "deluxe" in low:
        return "Deluxe"
    if "стандарт" in low or "standard" in low:
        return "Standard"
    if "семейн" in low or "family" in low:
        return "Family"
    if "suite" in low or "сьют" in low:
        return "Suite"
    return raw.capitalize()


def _dedupe_requested(items: list[RequestedAttribute]) -> list[RequestedAttribute]:
    """One entry per attribute key; must wins over should; constraints merge."""
    by_key: dict[str, RequestedAttribute] = {}
    for item in items:
        prev = by_key.get(item.key)
        if prev is None:
            by_key[item.key] = item
            continue
        role: Literal["must", "should"] = (
            "must" if "must" in {prev.role, item.role} else item.role
        )
        constraint = {**(prev.constraint or {}), **(item.constraint or {})}
        by_key[item.key] = RequestedAttribute(
            key=item.key,
            role=role,
            constraint=constraint,
            definition=item.definition or prev.definition,
        )
    return list(by_key.values())


def _merge_parsed(primary: ParsedQuery, secondary: ParsedQuery) -> ParsedQuery:
    """Fill missing keys/city/room from secondary (usually deterministic)."""
    keys = {r.key for r in primary.requested}
    merged = list(primary.requested)
    for r in secondary.requested:
        if r.key not in keys:
            merged.append(r)
    unsupported = list(primary.unsupported or [])
    seen_u = {(u.get("attribute_key") or u.get("key")) for u in unsupported}
    for u in secondary.unsupported or []:
        k = u.get("attribute_key") or u.get("key")
        if k not in seen_u:
            unsupported.append(u)
    return ParsedQuery(
        requested=_dedupe_requested(merged),
        city=primary.city or secondary.city,
        room_type=primary.room_type or secondary.room_type,
        unsupported=unsupported,
        extraction=primary.extraction
        if primary.extraction == "gigachat" or secondary.extraction != "gigachat"
        else "gigachat",
    )


def _apply_text_constraint_fixes(
    parsed: ParsedQuery,
    text: str,
    registry: AttributeRegistry,
) -> ParsedQuery:
    """Deterministic overlays: blackout negation, courtyard, metro without cap, contradictions."""
    requested = list(parsed.requested)
    by_key = {r.key: r for r in requested}
    unsupported = list(parsed.unsupported or [])
    room_type = parsed.room_type or _normalize_room_type(
        _ROOM_TYPE.search(text).group(1) if _ROOM_TYPE.search(text) else None
    )
    if _FAMILY_ROOM.search(text):
        room_type = "Family"

    # Metro near without minutes still requests walk evidence
    if re.search(r"(?i)метро|metro|subway", text) and "walk_to_metro" not in by_key:
        try:
            definition = registry.get("walk_to_metro")
            by_key["walk_to_metro"] = RequestedAttribute(
                key="walk_to_metro",
                role="must",
                constraint=dict(definition.constraint_defaults or {}),
                definition=definition,
            )
        except KeyError:
            pass

    # Blackout negation → equals=False. Do NOT treat «без клубов» as blackout negation.
    if _BLACKOUT_NEG.search(text):
        try:
            definition = registry.get("blackout_curtains")
            constraint = {
                **(definition.constraint_defaults or {}),
                "equals": False,
            }
            if room_type:
                constraint["room_type"] = room_type
            by_key["blackout_curtains"] = RequestedAttribute(
                key="blackout_curtains",
                role="must",
                constraint=constraint,
                definition=definition,
            )
        except KeyError:
            pass
    elif re.search(r"(?i)blackout|блэкаут|блекаут|плотн\w*\s+штор", text):
        # Positive blackout request (negation handled above). Keep should only if
        # the user explicitly said «should blackout».
        try:
            definition = (
                by_key["blackout_curtains"].definition
                if "blackout_curtains" in by_key
                else registry.get("blackout_curtains")
            )
        except KeyError:
            definition = None
        if definition is not None:
            c = dict(
                (by_key["blackout_curtains"].constraint if "blackout_curtains" in by_key else None)
                or definition.constraint_defaults
                or {}
            )
            c["equals"] = True
            if room_type:
                c.setdefault("room_type", room_type)
            want_should = bool(re.search(r"(?i)should\s+blackout|blackout\s*\(should\)", text))
            by_key["blackout_curtains"] = RequestedAttribute(
                key="blackout_curtains",
                role="should" if want_should else "must",
                constraint=c,
                definition=definition,
            )
    # Courtyard / «тихий двор»
    if re.search(r"(?i)двор|courtyard", text):
        try:
            definition = registry.get("courtyard_rooms")
            by_key["courtyard_rooms"] = RequestedAttribute(
                key="courtyard_rooms",
                role="must",
                constraint={**(definition.constraint_defaults or {}), "equals": True},
                definition=definition,
            )
        except KeyError:
            pass
        # Quiet courtyard also implies noise preference unless clubs requested
        if re.search(r"(?i)тих|спокойн|quiet", text) and "external_noise_risk" not in by_key:
            try:
                definition = registry.get("external_noise_risk")
                by_key["external_noise_risk"] = RequestedAttribute(
                    key="external_noise_risk",
                    role="must",
                    constraint={
                        **(definition.constraint_defaults or {}),
                        "prefer_risk": ["low", "medium"],
                    },
                    definition=definition,
                )
            except KeyError:
                pass

    # Quiet + club street without negation → contradiction (do not drop either silently)
    quiet = bool(re.search(r"(?i)тишин|тих(?:ий|ая|ое)|спокойн|quiet", text))
    club_pos = bool(_POS_CLUB_STREET.search(text)) and not _NEG_CLUB.search(text)
    if quiet and club_pos:
        unsupported.append(
            {
                "attribute_key": "contradiction_quiet_vs_nightlife",
                "status": "needs_clarification",
                "reason": "Request asks for quiet and nightlife street together",
            }
        )
        try:
            definition = registry.get("external_noise_risk")
            by_key["external_noise_risk"] = RequestedAttribute(
                key="external_noise_risk",
                role="must",
                constraint={
                    **(definition.constraint_defaults or {}),
                    "prefer_risk": ["low", "medium"],
                    "contradiction_nightlife": True,
                },
                definition=definition,
            )
        except KeyError:
            pass

    # «семейный номер» must not invent family_infrastructure alone
    if _FAMILY_ROOM.search(text) and not re.search(
        r"(?i)с\s+детьми|для\s+семьи|playground|парк", text
    ):
        by_key.pop("family_infrastructure", None)

    # Quiet / тихий → noise must
    if re.search(r"(?i)тишин|тих(?:ий|ая|ое|ие)|спокойн|quiet", text):
        if "external_noise_risk" in by_key:
            prev = by_key["external_noise_risk"]
            by_key["external_noise_risk"] = RequestedAttribute(
                key="external_noise_risk",
                role="must",
                constraint=dict(prev.constraint or {}),
                definition=prev.definition,
            )
        else:
            try:
                definition = registry.get("external_noise_risk")
                by_key["external_noise_risk"] = RequestedAttribute(
                    key="external_noise_risk",
                    role="must",
                    constraint={
                        **(definition.constraint_defaults or {}),
                        "prefer_risk": ["low", "medium"],
                    },
                    definition=definition,
                )
            except KeyError:
                pass

    # Prefer city token from the user text over LLM hallucinations
    city_m = _CITY.search(text)
    city = parsed.city
    if city_m:
        city = city_m.group(1)

    # Drop nonsensical room_type values invented by LLM (attribute keys, etc.)
    if room_type and room_type.lower().replace(" ", "_") in {
        "courtyard_rooms",
        "blackout_curtains",
        "external_noise_risk",
        "walk_to_metro",
        "family_infrastructure",
    }:
        room_type = None
    if _FAMILY_ROOM.search(text):
        room_type = "Family"
    elif _ROOM_TYPE.search(text):
        room_type = _normalize_room_type(_ROOM_TYPE.search(text).group(1)) or room_type

    return ParsedQuery(
        requested=_dedupe_requested(list(by_key.values())),
        city=city,
        room_type=room_type,
        unsupported=unsupported,
        extraction=parsed.extraction,
    )


def _gigachat_structured_extract(
    query: str,
    *,
    previous_query: str | None = None,
    conversation: list[dict[str, str]] | None = None,
    registry: AttributeRegistry | None = None,
) -> ParsedQuery | None:
    """Live GigaChat structured extract; None if unavailable or invalid."""
    try:
        from .gigachat_nlu import extract_hotel_wishes
    except Exception:
        return None
    reg = registry or build_default_registry(register_tools=False)
    known = list(reg.keys()) if hasattr(reg, "keys") else None
    extracted = extract_hotel_wishes(
        query,
        previous_query=previous_query,
        conversation=conversation,
        known_keys=known,
    )
    if extracted is None:
        return None

    requested: list[RequestedAttribute] = []
    for wish in extracted.wishes:
        try:
            definition = reg.get(wish.key)
        except KeyError:
            continue
        constraint = dict(definition.constraint_defaults or {})
        constraint.update(wish.constraint or {})
        if wish.key == "walk_to_metro":
            # Accept both max_minutes (LLM) and max_duration_min (matcher).
            # Do NOT drop metro wishes without a numeric cap («рядом с метро»).
            if "max_minutes" in constraint and "max_duration_min" not in constraint:
                constraint["max_duration_min"] = constraint["max_minutes"]
        if wish.key == "blackout_curtains" and "equals" not in constraint:
            constraint.setdefault("equals", True)
        requested.append(
            RequestedAttribute(
                key=wish.key,
                role=wish.role if wish.role in ("must", "should") else definition.default_role,  # type: ignore[arg-type]
                constraint=constraint,
                definition=definition,
            )
        )

    unsupported = [
        {"key": u, "reason": "gigachat_unsupported"}
        for u in (extracted.unsupported or [])
        if u
    ]
    room_type = _normalize_room_type(extracted.room_type)

    return ParsedQuery(
        requested=_dedupe_requested(requested),
        city=extracted.city,
        room_type=room_type,
        unsupported=unsupported,
        extraction="gigachat",
    )


def parse_query_structured(
    query: str,
    registry: AttributeRegistry | None = None,
    *,
    previous_query: str | None = None,
    conversation: list[dict[str, str]] | None = None,
    prefer_gigachat: bool = True,
) -> ParsedQuery:
    text = (query or "").strip()
    if not text:
        return ParsedQuery(requested=[])

    # Dialogue refinements: merge previous + current into one text for rules,
    # and pass both to GigaChat so constraints accumulate.
    combined = text
    if previous_query and previous_query.strip():
        combined = f"{previous_query.strip()}. Уточнение: {text}"

    reg = registry or build_default_registry(register_tools=False)

    # Always compute deterministic baseline (used alone or merged under GigaChat).
    det = _parse_deterministic(combined, reg)

    if prefer_gigachat:
        llm = _gigachat_structured_extract(
            text,
            previous_query=previous_query,
            conversation=conversation,
            registry=reg,
        )
        if llm is not None and (llm.requested or llm.city or llm.unsupported):
            if previous_query and not llm.requested:
                llm2 = _gigachat_structured_extract(
                    combined,
                    previous_query=None,
                    conversation=conversation,
                    registry=reg,
                )
                if llm2 is not None and llm2.requested:
                    llm = llm2
            merged = _merge_parsed(llm, det)
            return _apply_text_constraint_fixes(merged, combined, reg)

    return _apply_text_constraint_fixes(det, combined, reg)


def _parse_deterministic(combined: str, reg: AttributeRegistry) -> ParsedQuery:
    """Rule-based extract used as baseline / GigaChat merge source."""
    requested: list[RequestedAttribute] = []
    walk_cap = None
    m = _WALK_MAX_MIN.search(combined)
    if m:
        walk_cap = int(m.group(1))

    city_m = _CITY.search(combined)
    city = city_m.group(1) if city_m else None

    room_m = _ROOM_TYPE.search(combined)
    room_type = _normalize_room_type(room_m.group(1) if room_m else None)
    if _FAMILY_ROOM.search(combined):
        room_type = "Family"

    neg_clubs = bool(_NEG_CLUB.search(combined))
    blackout_neg = bool(_BLACKOUT_NEG.search(combined))
    want_parking = bool(re.search(r"(?i)парковк|parking", combined))
    no_street_cars = bool(
        re.search(r"(?i)без\s+машин|машин(?:ы|а)?\s+под\s+окн|no\s+cars?\s+under", combined)
    )
    text = combined

    unsupported: list[dict[str, str]] = []
    for pat, key, reason in _UNSUPPORTED_INTENTS:
        if pat.search(text):
            unsupported.append(
                {
                    "attribute_key": key,
                    "status": "unsupported",
                    "reason": reason,
                }
            )

    matched_keys: set[str] = set()
    for key in reg.keys():
        definition = reg.get(key)
        patterns = list(definition.intent_patterns or [])
        hit = any(re.search(pat, text) for pat in patterns if pat)
        if not hit:
            continue
        # Skip family_infrastructure for bare «семейный номер»
        if key == "family_infrastructure" and _FAMILY_ROOM.search(text) and not re.search(
            r"(?i)с\s+детьми|для\s+семьи|playground|парк", text
        ):
            continue
        matched_keys.add(key)
        role: Literal["must", "should"] = definition.default_role  # type: ignore[assignment]
        constraint: dict[str, Any] = dict(definition.constraint_defaults or {})
        if key in {"walk_to_metro", "walk_to_metro_entrance_min", "walk_to_metro_min"} and walk_cap is not None:
            constraint["max_duration_min"] = walk_cap
            constraint.setdefault("max_minutes", walk_cap)
        if key == "late_night_pharmacy_walk" and walk_cap is not None:
            constraint["max_duration_min"] = walk_cap
        if key == "external_noise_risk":
            constraint.setdefault("prefer_risk", ["low", "medium"])
            if neg_clubs:
                constraint["prefer_risk"] = ["low", "medium"]
                constraint["reject_risk"] = ["elevated"]
                constraint["reject_nightclub"] = True
        if key == "blackout_curtains":
            constraint["equals"] = False if blackout_neg else True
            if room_type:
                constraint["room_type"] = room_type
        if key == "courtyard_rooms":
            constraint.setdefault("equals", True)
        if key in {"car_access", "car_access_street", "parking_nearby"}:
            if want_parking:
                constraint["require_parking"] = True
            if no_street_cars:
                constraint["require_no_street_traffic"] = True
                role = "must"
        requested.append(
            RequestedAttribute(
                key=key,
                role=role,
                constraint=constraint,
                definition=definition,
            )
        )

    # Negation-only: "не возле клубов" without other quiet keywords still needs noise attr
    if neg_clubs and "external_noise_risk" not in matched_keys:
        try:
            definition = reg.get("external_noise_risk")
        except KeyError:
            definition = None
        if definition is not None:
            requested.append(
                RequestedAttribute(
                    key="external_noise_risk",
                    role=definition.default_role,  # type: ignore[arg-type]
                    constraint={
                        **(definition.constraint_defaults or {}),
                        "prefer_risk": ["low", "medium"],
                        "reject_risk": ["elevated"],
                        "reject_nightclub": True,
                    },
                    definition=definition,
                )
            )

    return ParsedQuery(
        requested=_dedupe_requested(requested),
        city=city,
        room_type=room_type,
        unsupported=unsupported,
        extraction="deterministic",
    )


def parse_query(
    query: str,
    registry: AttributeRegistry | None = None,
) -> list[RequestedAttribute]:
    # Offline/unit path: deterministic only (tests must not call live GigaChat).
    return parse_query_structured(
        query, registry=registry, prefer_gigachat=False
    ).requested


def search_hotels(
    store: IntelligenceStore,
    query: str,
    *,
    limit: int = 20,
    now: datetime | None = None,
    registry: AttributeRegistry | None = None,
    previous_query: str | None = None,
    conversation: list[dict[str, str]] | None = None,
    prefer_gigachat: bool = True,
    explain: bool = False,
) -> dict[str, Any]:
    at = now or datetime.now(timezone.utc)
    reg = registry or build_default_registry(register_tools=False)
    parsed = parse_query_structured(
        query,
        registry=reg,
        previous_query=previous_query,
        conversation=conversation,
        prefer_gigachat=prefer_gigachat,
    )
    requested = parsed.requested
    hotels = store.list_hotels()
    if parsed.city:
        city_l = parsed.city.lower()
        def _normalize_city_token(raw: str) -> str:
            t = raw.lower()
            if t.startswith("стамбул") or t.startswith("istanbul"):
                return "istanbul"
            if t.startswith("казан") or t.startswith("kazan"):
                return "kazan"
            if t.startswith("москв") or t.startswith("moscow"):
                return "moscow"
            if t.startswith("сочи") or t.startswith("sochi"):
                return "sochi"
            if t.startswith("анталь") or t.startswith("antalya"):
                return "antalya"
            if t.startswith("дуба") or t.startswith("dubai"):
                return "dubai"
            if t.startswith("праг") or t.startswith("prague"):
                return "prague"
            return t

        needle = _normalize_city_token(city_l)

        def _city_ok(h: dict[str, Any]) -> bool:
            blob = " ".join(
                str(h.get(k) or "")
                for k in ("city", "region", "country", "name", "canonical_name", "address")
            ).lower()
            if needle in blob:
                return True
            # Accept Russian/English city stems in hotel fields
            stems = {
                "istanbul": ("istanbul", "стамбул"),
                "kazan": ("kazan", "казан"),
                "moscow": ("moscow", "москв"),
                "sochi": ("sochi", "сочи"),
                "antalya": ("antalya", "анталь"),
                "dubai": ("dubai", "дуба"),
                "prague": ("prague", "праг"),
            }
            for stem in stems.get(needle, (needle,)):
                if stem in blob:
                    return True
            return False

        # Hard city filter: never fall back to other cities when a city was requested.
        hotels = [h for h in hotels if _city_ok(h)]
        city_filter_applied = True
        city_match_count = len(hotels)
    else:
        city_filter_applied = False
        city_match_count = len(hotels)

    results: list[HotelMatchExplanation] = []

    for hotel in hotels:
        expl = _evaluate_hotel(
            store,
            hotel,
            requested,
            now=at,
            registry=reg,
            unsupported=parsed.unsupported,
        )
        results.append(expl)

    def sort_key(item: HotelMatchExplanation) -> tuple:
        must_fail = any(
            u.get("role") == "must" for u in item.unmatched + item.unknown
        )
        return (1 if must_fail else 0, -item.score)

    results.sort(key=sort_key)
    limited = results[:limit]
    payload_results: list[dict[str, Any]] = []
    for r in limited:
        item: dict[str, Any] = {
            "hotel_id": r.hotel_id,
            "name": r.name,
            "score": r.score,
            "matched": r.matched,
            "unmatched": r.unmatched,
            "unknown": r.unknown,
            "conflicts": r.conflicts,
        }
        if explain and (r.matched or r.unknown or r.unmatched):
            try:
                from .gigachat_nlu import explain_from_evidence

                item["explanation"] = explain_from_evidence(
                    hotel_name=r.name or r.hotel_id,
                    query=query,
                    matched=r.matched,
                    unmatched=r.unmatched,
                    unknown=r.unknown,
                )
            except Exception:  # noqa: BLE001
                item["explanation"] = None
        payload_results.append(item)

    return {
        "query": query,
        "previous_query": previous_query,
        "extraction": parsed.extraction,
        "city": parsed.city,
        "city_filter_applied": city_filter_applied,
        "city_match_count": city_match_count,
        "room_type": parsed.room_type,
        "unsupported": parsed.unsupported,
        "requested": [
            {"key": r.key, "role": r.role, "constraint": r.constraint} for r in requested
        ],
        "results": payload_results,
        "note": (
            "no_hotels_in_requested_city"
            if city_filter_applied and city_match_count == 0
            else None
        ),
    }


def _pick_rows_for_request(
    rows: list[AttributeObservation],
    req: RequestedAttribute,
) -> list[AttributeObservation]:
    """Prefer room_type scope when query asks for a room type (blackout).

    If the query names Deluxe/Standard, do NOT treat another room_type as a match.
    Wrong-scope observations stay out of matched — caller reports unknown.
    """
    room_type = (req.constraint or {}).get("room_type")
    if req.key == "blackout_curtains" and room_type:
        want = str(room_type).lower()
        scoped = [
            r
            for r in rows
            if r.scope.kind == "room_type"
            and (r.scope.identifier or "").lower() == want
        ]
        if scoped:
            return scoped
        # Hotel-wide claim can answer any room type query
        hotel_rows = [r for r in rows if r.scope.kind == "hotel"]
        if hotel_rows:
            return hotel_rows
        # Explicitly requested room type missing → empty (unknown), not Deluxe fallback
        return []
    if req.key == "blackout_curtains":
        hotel_rows = [r for r in rows if r.scope.kind == "hotel"]
        if hotel_rows:
            return hotel_rows
        return rows
    hotel_rows = [r for r in rows if r.scope.kind == "hotel"]
    return hotel_rows or rows


def _evaluate_hotel(
    store: IntelligenceStore,
    hotel: dict[str, Any],
    requested: list[RequestedAttribute],
    *,
    now: datetime,
    registry: AttributeRegistry,
    unsupported: list[dict[str, str]] | None = None,
) -> HotelMatchExplanation:
    hotel_id = str(hotel.get("hotel_id") or hotel.get("id"))
    name = hotel.get("name") or hotel.get("canonical_name")
    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    score = 0.0

    for item in unsupported or []:
        unknown.append(
            {
                "attribute_key": item.get("attribute_key"),
                "role": "must",
                "reason": item.get("reason") or "unsupported",
                "status": "unsupported",
                "note": "unsupported ≠ match",
            }
        )

    for req in requested:
        rows = [
            r
            for r in store.list_observations(hotel_id, req.key)
            if r.scope.kind in {"hotel", "building", "room_type", "room"}
        ]
        hotel_rows = _pick_rows_for_request(rows, req)
        if not hotel_rows:
            unknown.append(
                {
                    "attribute_key": req.key,
                    "role": req.role,
                    "reason": "no_observation",
                    "note": "unknown ≠ match",
                }
            )
            continue

        same_scope = [r for r in hotel_rows if r.scope == hotel_rows[0].scope]
        resolution = resolve_observations(same_scope, now=now)
        if resolution.status == ClaimStatus.CONFLICTED:
            conflicts.append(
                {
                    "attribute_key": req.key,
                    "role": req.role,
                    "observation_ids": resolution.observation_ids,
                    "reason": resolution.reason,
                }
            )
            unmatched.append(
                {
                    "attribute_key": req.key,
                    "role": req.role,
                    "reason": "conflicted",
                }
            )
            continue

        if resolution.status in {ClaimStatus.UNKNOWN, ClaimStatus.STALE}:
            unknown.append(
                {
                    "attribute_key": req.key,
                    "role": req.role,
                    "reason": resolution.reason or resolution.status.value,
                    "note": "unknown ≠ match",
                }
            )
            continue

        preferred = next(
            (r for r in hotel_rows if r.observation_id == resolution.preferred_observation_id),
            hotel_rows[0],
        )

        definition = req.definition
        if definition is None:
            try:
                definition = registry.get(req.key)
            except KeyError:
                definition = AttributeDefinition(
                    key=req.key,
                    description="fallback definition for unmatched registry key",
                    value_type="any",
                    matcher="presence",
                )

        result, detail = match_constraint(definition, preferred, req.constraint)
        if result == "conflict":
            conflicts.append(
                {
                    "attribute_key": req.key,
                    "role": req.role,
                    "reason": detail,
                }
            )
            unmatched.append(
                {"attribute_key": req.key, "role": req.role, "reason": detail}
            )
            continue
        if result == "unknown":
            unknown.append(
                {
                    "attribute_key": req.key,
                    "role": req.role,
                    "reason": detail,
                    "note": "unknown ≠ match",
                }
            )
            continue
        if result == "match":
            weight = 2.0 if req.role == "must" else 1.0
            conf = preferred.confidence or 0.5
            status_boost = {"verified": 1.0, "estimated": 0.8, "unconfirmed": 0.5}.get(
                preferred.status.value, 0.4
            )
            score += weight * conf * status_boost
            entry: dict[str, Any] = {
                "attribute_key": req.key,
                "role": req.role,
                "value": preferred.value,
                "status": preferred.status.value,
                "confidence": preferred.confidence,
                "observation_id": preferred.observation_id,
                "detail": detail,
            }
            # Room-scoped blackout must disclose scope; never claim whole hotel
            if preferred.scope.kind in {"room_type", "room"}:
                entry["scope"] = preferred.scope.model_dump()
                if req.key == "blackout_curtains":
                    entry["hotel_wide"] = False
                    entry["detail"] = (
                        f"{detail}; scope={preferred.scope.kind}:"
                        f"{preferred.scope.identifier} (not whole hotel)"
                    )
            matched.append(entry)
        else:
            unmatched.append(
                {
                    "attribute_key": req.key,
                    "role": req.role,
                    "value": preferred.value,
                    "status": preferred.status.value,
                    "reason": detail,
                }
            )

    return HotelMatchExplanation(
        hotel_id=hotel_id,
        name=name,
        score=round(score, 4),
        matched=matched,
        unmatched=unmatched,
        unknown=unknown,
        conflicts=conflicts,
    )
