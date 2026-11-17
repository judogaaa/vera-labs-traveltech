"""Rule-based intent parsing.

Role: deterministic fallback + deterministic edits. It must NOT limit the
set of supported cities (CITY_HINTS is only a last-resort hint) and must NOT
override a valid GigaChat intent — the agent merges rule results carefully.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .models import HotelContext, Travelers, TripIntent, WishItem

# Last-resort hints only. Arbitrary destinations come from GigaChat/geocoder.
CITY_HINTS = [
    (r"\bказан\w*\b", "Казань"),
    (r"\bkazan\b", "Казань"),
    (r"\bтунис\w*\b", "Тунис"),
    (r"\btunis\b", "Тунис"),
    (r"\bлиссабон\w*\b", "Лиссабон"),
    (r"\blisbon\b", "Лиссабон"),
    (r"\bтбилис\w*\b", "Тбилиси"),
    (r"\btbilisi\b", "Тбилиси"),
    (r"\bсеул\w*\b", "Сеул"),
    (r"\bseoul\b", "Сеул"),
    (r"\bпариж\w*\b", "Париж"),
    (r"\bparis\b", "Париж"),
    (r"\bмоскв\w*\b", "Москва"),
    (r"\bпетербург\w*\b|\bспб\b", "Санкт-Петербург"),
    (r"\bантал\w*\b", "Antalya"),
    (r"\bantalya\b", "Antalya"),
    (r"\bдуба\w*\b", "Dubai"),
    (r"\bdubai\b", "Dubai"),
    (r"\bсингапур\w*\b", "Singapore"),
    (r"\bsingapore\b", "Singapore"),
    (r"\bстамбул\w*\b", "Istanbul"),
    (r"\bistanbul\b", "Istanbul"),
    (r"\bбангкок\w*\b", "Bangkok"),
    (r"\bbangkok\b", "Bangkok"),
    (r"\bшарм\w*\b", "Sharm el-Sheikh"),
    (r"сан[-\s]?франц\w*|сан[-\s]?фрациско|san\s*francisco", "San Francisco"),
    (r"нью[-\s]?йорк|new\s*york|\bnyc\b", "New York"),
    (r"лос[-\s]?анджелес|los\s*angeles", "Los Angeles"),
    (r"токио|tokyo", "Tokyo"),
    (r"праг\w*|prague", "Prague"),
    (r"барселон\w*|barcelona", "Barcelona"),
    (r"рим\b|rome\b", "Rome"),
    (r"лондон\w*|london", "London"),
    (r"берлин\w*|berlin", "Berlin"),
    (r"мадрид\w*|madrid", "Madrid"),
    (r"амстердам\w*|amsterdam", "Amsterdam"),
    (r"вена\b|vienna", "Vienna"),
    (r"будапешт\w*|budapest", "Budapest"),
    (r"пекин\w*|beijing", "Beijing"),
    (r"шанхай\w*|shanghai", "Shanghai"),
]

# Disambiguate common same-name cities for Nominatim.
GEOCODE_QUERY_ALIASES: dict[str, str] = {
    "san francisco": "San Francisco, California, USA",
    "сан-франциско": "San Francisco, California, USA",
    "сан франциско": "San Francisco, California, USA",
    "beijing": "Beijing, China",
    "пекин": "Beijing, China",
    "tokyo": "Tokyo, Japan",
    "токио": "Tokyo, Japan",
    "paris": "Paris, France",
    "париж": "Paris, France",
    "rome": "Rome, Italy",
    "рим": "Rome, Italy",
    "london": "London, United Kingdom",
    "лондон": "London, United Kingdom",
    "barcelona": "Barcelona, Spain",
    "барселона": "Barcelona, Spain",
    "prague": "Prague, Czechia",
    "прага": "Prague, Czechia",
    "dubai": "Dubai, United Arab Emirates",
    "дубай": "Dubai, United Arab Emirates",
    "new york": "New York, USA",
    "нью-йорк": "New York, USA",
}

KNOWN_CATEGORIES = {
    "attraction",
    "museum",
    "restaurant",
    "cafe",
    "bar",
    "park",
    "beach",
    "viewpoint",
    "shopping",
    "religious",
}

_VAGUE_ATTRACTION_LABELS = frozenset({"интересные места"})

# Natural-language wish → (provider category, canonical label).
# Order matters only for readability; matching is done by text position.
WISH_PATTERNS: list[tuple[str, str | None, str]] = [
    (
        r"кофе|кофейн|каф[еэ]|капучино|эспрессо|латте|\bcoffee\b|\bcafé\b|\bcafe\b",
        "cafe",
        "кофе",
    ),
    (r"морепродукты|морская кухня|seafood", "restaurant", "морепродукты"),
    (r"местная кухня|национальная кухня|грузинская кухня|традиционная кухня", "restaurant", "местная кухня"),
    (
        r"ресторан|покушать|поесть|поедим|вкусно|хороший ресторан|еда\b|кухн|обед|ужин|перекус|"
        r"тапас|рамэн|рамен|суши|пицц|стритфуд|street\s*food|"
        r"\brestaurant\b|\bfood\b|\beat\b|\bdinner\b|\blunch\b|\bramen\b|\bsushi\b|\btapas\b",
        "restaurant",
        "ресторан",
    ),
    (r"ночная жизнь|клуб\b|nightlife", "bar", "ночная жизнь"),
    (
        # (?![а-яё]) keeps «Барселона» from matching «бар».
        r"(?<![а-яё])бар(?![а-яё])|выпить|выпьем|пиво|коктейль|(?<![а-яё])вино(?![а-яё])|паб|"
        r"\bpub\b|\bbar\b|drinks?|beer|cocktail|wine|место .*выпить",
        "bar",
        "бар",
    ),
    (r"музей|галере|\bmuseum\b|\bgallery\b", "museum", "музей"),
    # Do not match «прогулка по Баумана» as a park — that is a named street walk.
    (r"парк|сквер|сад\b|\bpark\b", "park", "парк"),
    (r"пляж|море\b|покупаться|набережн|у моря|место у моря|\bbeach\b|\bsea\b", "beach", "пляж"),
    (
        r"шопинг|магазин|торговый центр|молл|outlet|shopping|\bmall\b|\bshops?\b",
        "shopping",
        "шопинг",
    ),
    (
        # Bare «марина» is handled as a named must (Dubai Marina), not a category dump.
        r"yacht\s*harbour|marina\s*walk",
        "attraction",
        "марина",
    ),
    (
        r"мечет|mosque|camii",
        "religious",
        "мечеть",
    ),
    (
        r"храм|церков|собор|синагог|temple|church|cathedral",
        "religious",
        "храм",
    ),
    (
        r"вид на город|красивый вид|смотров|панорам|смотровая|ночной город|ночной вид|"
        r"посмотреть на (?:ночной )?город|смотреть на город|огни города|"
        r"\bviewpoint\b|\bskyline\b|night (?:city|view)|city lights|look at (?:the )?city",
        "viewpoint",
        "смотровая",
    ),
    (r"романтич", "restaurant", "романтический ужин"),
    (
        r"интересн|куда сходить|куда ходить|не знаю куда|что посмотреть|"
        r"составь маршрут|маршрут на \d+|не знаю куда ходить",
        "attraction",
        "интересные места",
    ),
    (
        r"достопримечател|старый город|посмотреть город|атмосферные места|историческ|площадь|крепост|"
        r"attraction|old town|главн",
        "attraction",
        "достопримечательности",
    ),
]

MUST_PATTERNS: list[tuple[str, str]] = [
    # «кремль» as a whole word — not «Кремлёвская» street/metro alone.
    (r"казанск\w*\s+кремл|кремль\s+казан|kazan\s+kreml|\bkremlin\b|(?<![а-яё])кремль(?![а-яё])", "Кремль"),
    (r"бурдж[\s\-]?халиф|burj\s*khalifa", "Бурдж-Халифа"),
    (r"бауман", "Баумана"),
    (r"кул[\s\-]?шариф|kul[\s\-]?sharif", "Кул-Шариф"),
    (r"айя[\s\-]?софи|hagia\s*sophia|ayasofya", "Айя-София"),
    (r"голуб(ая|ой)\s+мечет|blue\s*mosque|султанахмет", "Голубая мечеть"),
    (r"галат\w*\s+башн|galata\s*tower|(?<![а-яё])галата(?![а-яё])", "Галата"),
    (r"калеич|kalei[cç]i|kaleici", "Калеичи"),
    (r"дубай\s*марин|dubai\s*marina|(?<![а-яё])марин[аы](?![а-яё])", "марина"),
    (r"карлов\s*мост|charles\s*bridge|karl[uů]v\s*most", "Карлов мост"),
    (r"староместск\w*\s*площад|old\s*town\s*square|staromest", "Староместская площадь"),
]


def _extract_days(text: str) -> int:
    t = text.lower()
    m = re.search(r"(\d+)\s*(дн|день|дня|дней|day|days?)", t)
    if m:
        return max(1, min(int(m.group(1)), 7))
    if re.search(r"на\s+один\s+день|один день|1\s*день|за\s+день", t):
        return 1
    if re.search(r"два дня|2\s*дня|пару дней|выходн", t):
        return 2
    return 1


def _extract_city_fallback(text: str, hotel: HotelContext | None) -> str:
    """Last-resort city guess. GigaChat + geocoder are the primary path."""
    for pattern, city in CITY_HINTS:
        if re.search(pattern, text, re.I):
            return city
    m = re.search(
        r"(?:приехал\w*|прилетел\w*|приехали|arrived\s+in|еду|едут|лечу|летим|буду|будем|живу|остановлюсь|хочу\s+в)\s+"
        r"(?:в\s+|in\s+)?"
        r"([А-ЯЁA-Za-z][А-Яа-яЁёA-Za-z\-]*(?:\s+[А-Яа-яЁёA-Za-z\-]{2,20}){0,2})"
        r"(?:\s+сегодня|\s+завтра|\s+на\b|\s+за\b|,|\.|$)",
        text,
        re.I,
    )
    if m:
        return m.group(1).strip(" .,!")
    m = re.search(
        r"(?:в|во|in)\s+([A-Za-zА-Яа-яёЁ][A-Za-zА-Яа-яёЁ\-]{2,30})\s+"
        r"(?:за\s+день|на\s+\d|сегодня|вечером|завтра)",
        text,
        re.I,
    )
    if m:
        return m.group(1).strip(" .,!")
    m = re.search(r"по\s+([A-Za-zА-Яа-яёЁ\-\s]{2,40}?)\s+на\s+\d+", text, re.I)
    if m:
        return m.group(1).strip(" .,!")
    m = re.search(r"в\s+([A-Za-zА-Яа-яёЁ\-\s]{2,40}?)\s+\d+\s*дн", text, re.I)
    if m:
        return m.group(1).strip(" .,!")
    if hotel and hotel.city:
        return hotel.city
    return ""


_HHMM_FLEX = re.compile(r"(\d{1,2})[:.](\d{2})")


def _normalize_hhmm(raw_h: str, raw_m: str) -> str | None:
    try:
        h, m = int(raw_h), int(raw_m)
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def extract_explicit_start_time(text: str) -> str | None:
    """Parse «с 10:00», «начало в 10:00», «start at 10:00». Beats time-of-day words."""
    t = text.lower()
    patterns = [
        r"(?:начал[оае]\s*(?:в|с)?|start(?:ing)?\s*(?:at|from)?|начина(?:ем|ю|ть)\s*(?:в|с)?)\s*",
        r"(?:^|[\s,;])с\s*",
    ]
    for prefix in patterns:
        m = re.search(prefix + r"(\d{1,2})[:.](\d{2})", t, re.I)
        if m:
            return _normalize_hhmm(m.group(1), m.group(2))
    # «в 10:00» / «at 10:00» but not «до 10:00» / «к 10:00» (those are return-by)
    m = re.search(r"(?<!до\s)(?<!к\s)(?:\bв|\bat)\s+(\d{1,2})[:.](\d{2})", t, re.I)
    if m:
        return _normalize_hhmm(m.group(1), m.group(2))
    return None


def _evening_means_day_start(text: str) -> bool:
    """True when the outing is evening-framed (not a daytime plan with one evening stop)."""
    if extract_explicit_start_time(text):
        # Explicit morning/afternoon clock → daytime plan; «вечером бар» is just a stop.
        return False
    t = text.lower()
    # Whole-evening framing.
    if re.search(
        r"вечерн\w*\s+маршрут|маршрут\s+на\s+вечер|\bна\s+вечер\b|\btonight\b|"
        r"куда сходить вечером|сходить вечером|сегодня .*вечер|"
        r"ночной город|ночной вид|огни города|this evening",
        t,
    ):
        return True
    # Strip only «вечером <food/drink stop>» so a single evening wish doesn't
    # move a daytime sightseeing plan to 18:00.
    stripped = re.sub(
        r"вечером\s+(?:бар|ресторан|кафе|музей|парк|пляж|кофе|выпить)\w*",
        " ",
        t,
    )
    stripped = re.sub(r"in\s+the\s+evening\s+\w+", " ", stripped)
    if re.search(r"вечер|\bevening\b|\bночн", stripped):
        if re.search(r"\bутр|\bднём|\bднем|достопримечател|музей|парк|пляж|старый город", t):
            return False
        return True
    return False


def _extract_time_of_day(text: str) -> str | None:
    """Soft day-start hint. Explicit clocks and wish-scoped «вечером» win over this."""
    if extract_explicit_start_time(text):
        return None
    t = text.lower()
    if _evening_means_day_start(text):
        return "18:00"
    if re.search(r"\bутр|\bутром\b|\bmorning\b", t):
        return "09:00"
    if re.search(r"\bночь\b|\bночью\b|\bночн", t):
        return "20:00"
    return None


def _dedupe_wish_hits(found: list[tuple[int, WishItem]]) -> list[tuple[int, WishItem]]:
    found.sort(key=lambda x: x[0])
    wishes: list[tuple[int, WishItem]] = []
    seen_cats: set[str] = set()
    for pos, w in found:
        cat = w.category
        # Attraction: keep a specific label over vague «интересные места».
        if cat == "attraction":
            existing_attr = next(
                ((i, p, x) for i, (p, x) in enumerate(wishes) if x.category == "attraction"),
                None,
            )
            if existing_attr is not None:
                i, _p, prev = existing_attr
                if prev.label in _VAGUE_ATTRACTION_LABELS and w.label not in _VAGUE_ATTRACTION_LABELS:
                    wishes[i] = (pos, w)
                continue
        elif cat and cat in seen_cats and w.kind != "must":
            # One wish per concrete category («покушать вкусно» → one restaurant).
            continue
        if (
            wishes
            and wishes[-1][1].category == w.category
            and wishes[-1][1].kind == w.kind
            and wishes[-1][1].label == w.label
        ):
            continue
        wishes.append((pos, w))
        if cat:
            seen_cats.add(cat)
    return wishes


def extract_wish_sequence(text: str) -> list[WishItem]:
    """Ordered user wishes by position in text. No city limitation."""
    return [w for _, w in extract_wish_sequence_with_pos(text)]


def extract_wish_sequence_with_pos(text: str) -> list[tuple[int, WishItem]]:
    """(position, wish) pairs for order-aware merging with GigaChat intents."""
    found: list[tuple[int, WishItem]] = []
    for pattern, category, label in WISH_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            found.append((m.start(), WishItem(label=label, kind="interest", category=category, query=label)))
    for pattern, name in MUST_PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            found.append((m.start(), WishItem(label=name, kind="must", category=None, query=name)))
    wishes = _dedupe_wish_hits(found)
    cats = {w.category for _, w in wishes if w.category}
    concrete = cats & {
        "restaurant",
        "bar",
        "cafe",
        "viewpoint",
        "museum",
        "beach",
        "park",
        "shopping",
        "religious",
    }
    has_named_must = any(w.kind == "must" for _, w in wishes)
    # Vague «куда сходить» must not crowd out F&B / concrete stops.
    # Named musts (Калеичи, Бурдж…) already cover sightseeing — drop vague attraction fill.
    if concrete or has_named_must:
        wishes = [
            (pos, w)
            for pos, w in wishes
            if not (w.category == "attraction" and w.label in _VAGUE_ATTRACTION_LABELS)
        ]
    if has_named_must:
        wishes = [
            (pos, w)
            for pos, w in wishes
            if not (
                w.category == "attraction"
                and w.kind != "must"
                and w.label == "достопримечательности"
            )
        ]
    return wishes


def _extract_interests(text: str) -> list[str]:
    wishes = extract_wish_sequence(text)
    found = list(dict.fromkeys(w.category for w in wishes if w.category))
    # Only inject museum on sightseeing days — not on evening food/nightlife crawls.
    dining = bool({"restaurant", "bar", "cafe"} & set(found))
    if "attraction" in found and "museum" not in found and not dining:
        found.append("museum")
    if not found:
        found = ["attraction", "museum"]
    return found


def _looks_like_evening_wish_set(wishes: list[WishItem]) -> bool:
    cats = {w.category for w in wishes if w.category}
    if not cats:
        return False
    eveningish = {"restaurant", "bar", "cafe", "viewpoint"}
    return bool(cats & {"bar", "cafe"}) and cats <= eveningish | {"attraction"}


def detect_edit_action(text: str) -> tuple[str | None, str | None]:
    """Single primary edit action (back-compat)."""
    actions = parse_edit_actions(text)
    for kind in ("remove_stop", "add_stop", "replace_stop"):
        for action, target in actions:
            if action == kind:
                return action, target
    return (actions[0] if actions else (None, None))


def _parse_replace_directive(text: str) -> tuple[str, str | None] | None:
    """Return (old_target, new_query|None) for «замени(те) X на Y» / «вместо X»."""
    t = text.lower().strip()
    m = re.search(
        r"замени(?:те)?\s+(.+?)\s+на\s+(.+?)(?:\s+и\s+|\s*,\s*|[.!?]*$)",
        t,
    )
    if m:
        old = m.group(1).strip(" .!")
        new = m.group(2).strip(" .!")
        if old:
            return old, (new or None)
    m = re.search(r"замени(?:те)?\s+(.+?)$", t)
    if m:
        old = m.group(1).strip(" .!")
        if old and " на " not in f" {old} ":
            return old, None
        if " на " in old:
            left, _, right = old.partition(" на ")
            if left.strip():
                return left.strip(" .!"), right.strip(" .!") or None
    m = re.search(r"вместо\s+(.+?)(?:\s+на\s+(.+?))?(?:\s+и\s+|\s*,\s*|[.!?]*$)", t)
    if m:
        old = m.group(1).strip(" .!")
        new = (m.group(2) or "").strip(" .!") or None
        if old:
            return old, new
    if re.search(r"\bвместо\b|\bзамени", t):
        return t, None
    return None


def _is_keep_as_is(text: str) -> bool:
    """True for acknowledgements that must not rebuild or strip the trip."""
    t = text.lower().strip()
    return bool(
        re.search(
            r"без\s+изменен|"
            r"оставь(?:те)?\s+(?:как\s+есть|маршрут\s+без)|"
            r"ничего\s+не\s+(?:меня|трог)|"
            r"не\s+меняй(?:те)?|"
            r"вс[её]\s+(?:отлично|хорошо|ок)|"
            r"^(?:ok|ок|хорошо|спасибо|ладно)[.!]*$",
            t,
        )
    )


def parse_edit_actions(text: str) -> list[tuple[str | None, str | None]]:
    """All edit directives in one message, e.g. 'Добавь парк и убери музей'."""
    t = text.lower()
    # Keep-as-is must win over the chat fallback that re-plans when editAction
    # is null — otherwise «без изменений» silently rebuilds the itinerary.
    if _is_keep_as_is(t) and not re.search(
        r"убери|удали|добавь|замени|перестрой|заново|rebuild",
        t,
    ):
        return [("keep_as_is", None)]
    actions: list[tuple[str | None, str | None]] = []
    end = r"(?=\s+и\s+|\s*,\s*|\s+а\s+также\s+|[.!?]*$)"
    for m in re.finditer(
        r"(?:убери(?:те)?|удали(?:ть)?)\s+([^,.]+?)" + end,
        t,
    ):
        target = m.group(1).strip(" .!")
        if target:
            actions.append(("remove_stop", target))
    # «без X» only for concrete stop categories — never meta phrases like
    # «без изменений», «без долгих переездов», «без лишнего».
    for m in re.finditer(r"\bбез\s+([^,.]+?)" + end, t):
        target = m.group(1).strip(" .!")
        if not target:
            continue
        if re.search(
            r"изменен|правок|правки|долг|лишн|переезд|пеш|ход|переход|машин|такси|авто",
            target,
        ):
            continue
        if not re.search(
            r"музе|парк|ресторан|бар|кафе|пляж|достопримечател|остановк|место|"
            r"attraction|museum|park|restaurant|bar|cafe|beach",
            target,
        ):
            continue
        actions.append(("remove_stop", target))
    for m in re.finditer(
        r"добавь(?:те)?|добавить",
        t,
    ):
        m2 = re.search(
            r"добавь(?:те)?\s+([^,.]+?)" + end,
            t[m.start() :],
        )
        if m2 and m2.group(1).strip(" .!"):
            actions.append(("add_stop", m2.group(1).strip(" .!")))
    replace = _parse_replace_directive(t)
    if replace:
        actions.append(("replace_stop", replace[0]))
    if re.search(r"верн\w+\s+в\s+отел|до\s+\d{1,2}:\d{2}|к\s+\d{1,2}:\d{2}", t):
        actions.append(("return_by", text))
    if re.search(r"слишком много ходить|меньше ходить|не хочу много ходить|без долгих|на машине|такси", t):
        actions.append(("change_transport", text))
    if re.search(r"с ребён|с ребен|дети|детск", t):
        actions.append(("with_child", text))
    if re.search(r"перестрой|заново|rebuild", t):
        actions.append(("rebuild_day", text))
    # Clarifications that list more places / complain about coverage → rebuild.
    if re.search(
        r"почему\s+одно|мало\s+мест|одно\s+место|нужно\s+(?:больше|ещё|еще)|"
        r"я\s+сказал|я\s+просил|найди\s+(?:ещё|еще|ресторан|бар)|"
        r"find\s+(?:a\s+)?restaurant|more\s+places",
        t,
    ):
        actions.append(("rebuild_day", text))
    return actions


def parse_replace_targets(text: str) -> tuple[str | None, str | None]:
    """(old_target, new_query) for replace edits."""
    parsed = _parse_replace_directive(text.lower())
    if not parsed:
        return None, None
    return parsed


def parse_intent_rule_based(
    message: str,
    hotel: HotelContext | None = None,
    existing: TripIntent | None = None,
) -> TripIntent:
    base = existing.model_copy(deep=True) if existing else TripIntent()
    city = _extract_city_fallback(message, hotel) or base.destination
    days = _extract_days(message)
    interests = _extract_interests(message)
    action, target = detect_edit_action(message)
    replace_old, replace_new = parse_replace_targets(message)
    if action == "replace_stop" and replace_old:
        target = replace_old
    # Edit messages like «убери музей» still match wish patterns — keep the
    # trip's wish list unless the user asked to rebuild / add.
    if existing and action and action not in {None, "rebuild_day", "add_stop"}:
        wishes = list(existing.wishSequence)
    else:
        wishes = extract_wish_sequence(message)
        if existing and not wishes:
            wishes = list(existing.wishSequence)
    must_visit = list(base.mustVisit)
    for pattern, name in MUST_PATTERNS:
        if re.search(pattern, message, re.I) and name not in must_visit:
            must_visit.append(name)

    return_by = base.returnBy
    m = re.search(r"(?:до|к)\s*(\d{1,2}:\d{2})", message)
    if m:
        return_by = m.group(1)
        if len(return_by.split(":")[0]) == 1:
            return_by = f"0{return_by}"

    start_time = base.startTime
    end_time = return_by or base.endTime
    explicit_start = extract_explicit_start_time(message)
    if explicit_start:
        start_time = explicit_start
    else:
        tod = _extract_time_of_day(message)
        if tod and (not existing or action in {None, "rebuild_day"}):
            start_time = tod
        elif (
            (not existing or action == "rebuild_day")
            and _looks_like_evening_wish_set(wishes)
            and start_time in {"", "10:00"}
        ):
            start_time = "18:00"
    # Evening crawls need a late window so restaurant → bar → viewpoint fit.
    if start_time >= "17:00" and (not return_by) and (not existing or end_time <= "20:00"):
        end_time = "23:30"

    travelers = base.travelers
    if action == "with_child" or re.search(r"ребён|ребен|лет", message, re.I):
        age_m = re.search(r"(\d+)\s*лет", message)
        ages = [int(age_m.group(1))] if age_m else [6]
        travelers = Travelers(adults=max(travelers.adults, 2), children=ages)

    transport = base.transportPreference
    if action == "change_transport" or re.search(r"на машине|авто|такси", message, re.I):
        transport = "car"
    if re.search(r"пешком", message, re.I):
        transport = "walk"

    pace = base.pace
    if travelers.children:
        pace = "relaxed"
    if re.search(r"без лишних переездов|удобный|спокойн|не спеша", message, re.I):
        pace = "relaxed"

    budget = base.budget
    bm = re.search(r"(\d[\d\s]{1,12})\s*(€|eur|usd|\$|руб|₽|сом|лари|tnd|tnd)", message, re.I)
    if bm:
        try:
            budget = float(bm.group(1).replace(" ", ""))
        except ValueError:
            budget = base.budget

    # Clarification rebuild: merge newly named wishes into the existing list.
    if existing and action == "rebuild_day" and wishes:
        by_cat = {w.category: w for w in existing.wishSequence if w.category}
        for w in wishes:
            if w.category:
                by_cat[w.category] = w
        # Prefer the clarification order when it lists concrete categories.
        if len(wishes) >= 2:
            merged = list(wishes)
            for w in existing.wishSequence:
                if w.category and w.category not in {x.category for x in merged}:
                    merged.append(w)
            wishes = merged
        else:
            wishes = list(by_cat.values()) or wishes

    return TripIntent(
        destination=city,
        days=days if not existing else (days if re.search(r"\d+\s*дн", message.lower()) else base.days),
        startTime=start_time,
        endTime=end_time,
        interests=interests if not existing or action in {None, "rebuild_day", "add_stop"} else list(dict.fromkeys(base.interests + interests)),
        wishSequence=wishes,
        avoid=base.avoid,
        travelers=travelers,
        transportPreference=transport,
        budget=budget,
        pace=pace,
        mustVisit=must_visit,
        returnBy=return_by,
        editAction=action,
        editTarget=target,
        editReplacement=replace_new if action == "replace_stop" else None,
    )


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def normalize_intent(data: dict[str, Any]) -> TripIntent:
    """Validate + normalize a GigaChat-produced intent dict. Never invents facts."""
    d = dict(data or {})
    dest = str(d.get("destination") or "").strip()
    days = d.get("days", 1)
    try:
        days = max(1, min(int(days), 7))
    except (TypeError, ValueError):
        days = 1
    start = str(d.get("startTime") or "10:00").strip()
    if not _HHMM.match(start):
        start = "10:00"
    end = str(d.get("endTime") or d.get("returnBy") or "20:00").strip()
    if not _HHMM.match(end):
        end = "20:00"
    interests: list[str] = []
    for item in d.get("interests") or []:
        key = str(item).strip().lower()
        if key in KNOWN_CATEGORIES and key not in interests:
            interests.append(key)
    wishes: list[WishItem] = []
    for item in d.get("wishSequence") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        cat = item.get("category")
        cat = str(cat).strip().lower() if cat else None
        if cat not in KNOWN_CATEGORIES:
            cat = None
        kind = str(item.get("kind") or "interest").strip().lower()
        if kind not in {"interest", "must"}:
            kind = "interest"
        wishes.append(
            WishItem(label=label, kind=kind, category=cat, query=str(item.get("query") or label).strip())
        )
    if not interests:
        interests = list(dict.fromkeys([w.category for w in wishes if w.category])) or ["attraction"]
    transport = str(d.get("transportPreference") or "walk").strip().lower()
    if transport not in {"walk", "car", "transit", "mixed"}:
        transport = "walk"
    pace = str(d.get("pace") or "normal").strip().lower()
    if pace not in {"relaxed", "normal", "intensive"}:
        pace = "normal"
    travelers = d.get("travelers") if isinstance(d.get("travelers"), dict) else {}
    try:
        adults = max(1, int(travelers.get("adults", 2)))
    except (TypeError, ValueError):
        adults = 2
    children: list[int] = []
    for c in travelers.get("children", []) or []:
        try:
            children.append(max(0, min(int(c), 17)))
        except (TypeError, ValueError):
            continue
    budget = d.get("budget")
    try:
        budget = float(budget) if budget is not None else None
    except (TypeError, ValueError):
        budget = None
    ret = d.get("returnBy")
    ret = str(ret).strip() if ret else None
    if ret and not _HHMM.match(ret):
        ret = None
    return TripIntent(
        destination=dest,
        days=days,
        startTime=start,
        endTime=ret or end,
        interests=interests,
        wishSequence=wishes,
        avoid=[str(a) for a in (d.get("avoid") or [])][:20],
        travelers=Travelers(adults=adults, children=children),
        transportPreference=transport,  # type: ignore[arg-type]
        budget=budget,
        pace=pace,  # type: ignore[arg-type]
        mustVisit=[str(x) for x in (d.get("mustVisit") or [])][:20],
        returnBy=ret,
        editAction=d.get("editAction"),
        editTarget=d.get("editTarget"),
        editReplacement=d.get("editReplacement"),
    )


def validate_intent(data: dict[str, Any]) -> TripIntent:
    return TripIntent.model_validate(data)


def try_parse_json_intent(raw: str) -> TripIntent | None:
    text = raw.strip()
    # extract JSON object if wrapped in markdown
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return validate_intent(data)
    except Exception:  # noqa: BLE001
        return None
