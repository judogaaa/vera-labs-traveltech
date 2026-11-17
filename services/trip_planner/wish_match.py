"""Strict named-wish matching: aliases, scoring, dedup.

Category «attraction» never fulfills a named must like «Бурдж-Халифа».
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from .models import Place, WishItem

# Canonical must label → multilingual aliases (lowercase after normalize).
NAMED_ALIASES: dict[str, list[str]] = {
    "Кремль": [
        "казанский кремль",
        "kazan kremlin",
        "kremlin of kazan",
        "kreml kazan",
        "казань кремль",
    ],
    "Баумана": [
        "улица баумана",
        "баумана",
        "bauman street",
        "ulitsa baumana",
        "baumana street",
        "пешеходная улица баумана",
    ],
    "Кул-Шариф": [
        "кул шариф",
        "кул-шариф",
        "kul sharif",
        "qolsharif",
        "мечеть кул шариф",
    ],
    "Айя-София": [
        "айя софия",
        "айя-софия",
        "hagia sophia",
        "ayasofya",
        "aya sofya",
        "аясофья",
    ],
    "Голубая мечеть": [
        "голубая мечеть",
        "blue mosque",
        "sultan ahmed mosque",
        "sultan ahmet mosque",
        "sultanahmet camii",
        "sultan ahmed",
        "султанахмет мечеть",
    ],
    "Гранд базар": [
        "гранд базар",
        "большой базар",
        "grand bazaar",
        "kapalı çarşı",
        "kapali carsi",
        "covered bazaar",
        "grand bazar istanbul",
    ],
    "Галата": [
        "галатская башня",
        "galata tower",
        "galata kulesi",
        "галата",
    ],
    "Бурдж-Халифа": [
        "бурдж халифа",
        "бурдж-халифа",
        "burj khalifa",
        "برج خليفة",
        "burj khalifa dubai",
    ],
    "марина": [
        "dubai marina",
        "дубай марина",
        "مرسى دبي",
        "marina dubai",
        "дубайская марина",
    ],
    "Калеичи": [
        "калеичи",
        # Prefer diacritic Latin — Nominatim returns 0 hits for plain "Kaleici Antalya".
        "kaleiçi",
        "Kaleiçi",
        "kaleici",
        "kaleiçi old town",
        "kaleici antalya",
        "antalya kaleici",
        "antalya old town",
        "старый город калеичи",
        "старый город антальи",
    ],
    "Карлов мост": [
        "карлов мост",
        "charles bridge",
        "karluv most",
        "karlův most",
    ],
    "Староместская площадь": [
        "староместская площадь",
        "old town square",
        "staromestske namesti",
        "staroměstské náměstí",
        "староместская",
    ],
}

# Wikidata Q-ids that pin a must to a unique place when present.
NAMED_WIKIDATA: dict[str, set[str]] = {
    "Кремль": {"Q183383", "Q603622"},
    "Кул-Шариф": {"Q1542311"},
    "Айя-София": {"Q12506"},
    "Голубая мечеть": {"Q182170"},
    "Гранд базар": {"Q461058"},
    "Галата": {"Q216954"},
    "Бурдж-Халифа": {"Q4555", "Q12495"},
    "марина": {"Q1263703", "Q2915544", "Q1135647"},
    "Баумана": {"Q2381114"},
    "Карлов мост": {"Q18931", "Q204871"},
    "Староместская площадь": {"Q193631", "Q421678"},
    "Калеичи": {"Q5994531"},
}

MUST_SCORE_THRESHOLD = 0.78
DEDUP_METERS = 140.0

# District / old-town / neighbourhood wishes — a museum or hotel inside the area
# must not count as the area itself (universal, not city-specific).
_AREA_ALIAS_MARKERS = (
    "old town",
    "старый город",
    "historic centre",
    "historic center",
    "historical center",
    "altstadt",
    "centro storico",
    "neighbourhood",
    "neighborhood",
    "quarter",
)
_AREA_PLACE_KINDS = frozenset(
    {
        "suburb",
        "neighbourhood",
        "neighborhood",
        "quarter",
        "city_block",
        "borough",
        "district",
        "pedestrian",
        "boundary",
        "place",
    }
)
_TENANT_NAME_TOKENS = frozenset(
    {
        "museum",
        "muze",
        "müze",
        "hotel",
        "hostel",
        "restaurant",
        "cafe",
        "café",
        "bar",
        "mall",
        "shop",
        "otel",
        "butik",
        "meyhan",
        "pizza",
        "coffee",
        "steak",
        "gastro",
        "stays",
        "museum",
        "музей",
        "отель",
        "гостиниц",
        "ресторан",
        "кафе",
    }
)
_TENANT_CATEGORIES = frozenset({"museum", "cafe", "restaurant", "bar", "hotel", "shopping"})


def normalize_name(text: str) -> str:
    s = (text or "").strip().lower().replace("ё", "е")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ı", "i").replace("İ", "i")
    s = re.sub(r"[«»\"'`ʼ]", "", s)
    s = re.sub(r"[-_/.,:;()+]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _token_set(s: str) -> set[str]:
    return {t for t in normalize_name(s).split() if len(t) >= 3}


def _phrase_in_name(hay: str, needle: str) -> bool:
    """True if needle appears as whole word(s), not a stem of a longer token.

    «кремль» must not match «кремлёвская»; «blue mosque» may match inside a longer title.
    """
    if not hay or not needle:
        return False
    if hay == needle:
        return True
    if needle in hay:
        idx = 0
        while True:
            pos = hay.find(needle, idx)
            if pos < 0:
                return False
            before_ok = pos == 0 or not hay[pos - 1].isalnum()
            end = pos + len(needle)
            after_ok = end >= len(hay) or not hay[end].isalnum()
            if before_ok and after_ok:
                return True
            idx = pos + 1
    return False


# Single-token aliases that are too generic for a high score alone.
_WEAK_SINGLE_ALIASES = frozenset(
    {
        "марина",
        "marina",
        "кремль",
        "kremlin",
        "old town",
        "старый город",
    }
)


def canonical_named_label(label: str) -> str | None:
    """Map a free-text label to a NAMED_ALIASES key when possible."""
    n = normalize_name(label or "")
    if not n:
        return None
    for k in NAMED_ALIASES:
        if normalize_name(k) == n:
            return k
    # Longer aliases first so «dubai marina» wins over bare «marina».
    pairs: list[tuple[str, str]] = []
    for k, aliases in NAMED_ALIASES.items():
        pairs.append((k, normalize_name(k)))
        for a in aliases:
            pairs.append((k, normalize_name(a)))
    pairs.sort(key=lambda kv: len(kv[1]), reverse=True)
    for k, an in pairs:
        if not an or len(an) < 4:
            continue
        if n == an or _phrase_in_name(n, an):
            return k
    return None


def aliases_for(label: str) -> list[str]:
    key = (label or "").strip()
    canon = canonical_named_label(key) or key
    out = list(NAMED_ALIASES.get(canon, []))
    n = normalize_name(canon)
    if n and n not in out:
        out.insert(0, n)
    for k, vals in NAMED_ALIASES.items():
        if normalize_name(k) == n:
            for v in vals:
                if v not in out:
                    out.append(v)
    return out


def is_named_must(wish: WishItem) -> bool:
    """True for a concrete landmark wish — never for vague «достопримечательности»."""
    label = (wish.label or "").strip()
    if not label:
        return False
    text = f"{label} {wish.query or ''}".lower()
    vague = (
        "достопримечатель",
        "sightseeing",
        "attractions",
        "sights",
        "что посмотреть",
        "главные места",
    )
    if any(m in text for m in vague):
        return False
    bare_cats = {
        "attraction",
        "museum",
        "park",
        "cafe",
        "restaurant",
        "bar",
        "beach",
        "shopping",
        "viewpoint",
        "religious",
        "музей",
        "парк",
        "кафе",
        "ресторан",
        "пляж",
    }
    if label.lower() in bare_cats:
        return False
    if canonical_named_label(label) or canonical_named_label(wish.query or ""):
        return True
    # Concrete mustVisit-style labels (proper names) without a category fill.
    return wish.kind == "must" and wish.category is None


def name_match_score(place_name: str, label: str, extra_aliases: list[str] | None = None) -> float:
    """0..1 score. Short shared stems («кремл») are not enough."""
    hay = normalize_name(place_name)
    if not hay:
        return 0.0
    aliases = aliases_for(label)
    if extra_aliases:
        aliases = list(dict.fromkeys(aliases + [normalize_name(a) for a in extra_aliases if a]))
    best = 0.0
    hay_toks = _token_set(hay)
    for alias in aliases:
        an = normalize_name(alias)
        if not an:
            continue
        if hay == an:
            best = max(best, 1.0)
            continue
        # Only the explicitly generic tokens are weak — not every short proper name.
        weak = an in _WEAK_SINGLE_ALIASES
        # Place name contained in a longer alias (rare) or alias as whole phrase in name.
        if len(an) >= 5 and _phrase_in_name(hay, an):
            if weak and an != hay and not any(
                _phrase_in_name(hay, normalize_name(strong))
                for strong in aliases
                if len(normalize_name(strong).split()) >= 2
            ):
                # «marina» inside «dubai creek harbour marina» is not Dubai Marina.
                best = max(best, 0.55)
            else:
                best = max(best, 0.92 if len(an) >= 8 else 0.86)
            continue
        if len(hay) >= 5 and len(an) >= 8 and _phrase_in_name(an, hay):
            best = max(best, 0.88)
            continue
        a_toks = _token_set(an)
        if not a_toks:
            continue
        inter = hay_toks & a_toks
        if not inter:
            continue
        # Require majority of alias tokens, not a single short token.
        ratio = len(inter) / max(len(a_toks), 1)
        if ratio >= 0.8 and (len(inter) >= 2 or max(len(t) for t in inter) >= 6):
            best = max(best, 0.8 + 0.15 * ratio)
        elif ratio >= 1.0 and len(a_toks) == 1 and max(len(t) for t in a_toks) >= 6:
            # Single long token must be an exact token of the place name.
            if inter <= hay_toks and next(iter(a_toks)) in hay.split():
                if weak:
                    best = max(best, 0.55)
                else:
                    best = max(best, 0.82)
    return best


def wikidata_match(place: Place, label: str) -> bool:
    qid = (place.wikidataId or "").strip()
    if not qid:
        return False
    wanted = NAMED_WIKIDATA.get(label.strip()) or NAMED_WIKIDATA.get(
        next((k for k in NAMED_WIKIDATA if normalize_name(k) == normalize_name(label)), ""),
        set(),
    )
    return qid in wanted


def wish_targets_area(label: str) -> bool:
    """True when the wish names a district / old town / neighbourhood, not a building."""
    canon = canonical_named_label(label) or label
    aliases = aliases_for(canon)
    blob = " ".join(normalize_name(a) for a in [canon, label, *aliases] if a)
    if any(m in blob for m in _AREA_ALIAS_MARKERS):
        return True
    # Short toponyms used as districts (Калеичи, Галата as quarter) — if an alias
    # is exactly the short name and another alias mentions old town, already True.
    return False


def _is_tenant_of_named_area(place: Place, label: str) -> bool:
    """Museum/hotel/cafe that merely contains the district name in its title."""
    if wikidata_match(place, label):
        return False
    kind = (place.placeKind or "").lower()
    if kind in _AREA_PLACE_KINDS:
        return False
    if kind in {
        "museum",
        "hotel",
        "hostel",
        "restaurant",
        "cafe",
        "bar",
        "fast_food",
        "fire_station",
        "pub",
        "motel",
        "guest_house",
    }:
        return True
    pname = normalize_name(place.name)
    tokens = set(pname.split())
    if tokens & _TENANT_NAME_TOKENS:
        return True
    if place.category in _TENANT_CATEGORIES:
        # Name is longer than the best alias → "X Museum" / "X Hotel", not X itself.
        aliases = [normalize_name(a) for a in aliases_for(label) if normalize_name(a)]
        if not aliases:
            return False
        best = max(aliases, key=len)
        if best and _phrase_in_name(pname, best) and len(pname) > len(best) + 4:
            return True
    return False


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class RankedPlace:
    place: Place
    score: float
    matched_alias: str
    distance_m: float


def rank_named_candidates(
    places: list[Place],
    label: str,
    *,
    near_lat: float,
    near_lon: float,
    query: str = "",
    max_distance_m: float = 25_000,
) -> list[RankedPlace]:
    extras = [query] if query else []
    area_wish = wish_targets_area(label) or wish_targets_area(query or "")
    ranked: list[RankedPlace] = []
    for p in places:
        dist = haversine_m(near_lat, near_lon, p.lat, p.lon)
        if dist > max_distance_m:
            continue
        # District wish: skip tenants (museum/hotel/cafe named after the area).
        if area_wish and _is_tenant_of_named_area(p, label):
            continue
        score = name_match_score(p.name, label, extras)
        if p.description:
            score = max(score, name_match_score(p.description, label, extras) * 0.95)
        if wikidata_match(p, label):
            score = max(score, 0.98)
        pname = normalize_name(p.name)
        kind = (p.placeKind or "").lower()
        if area_wish and kind in _AREA_PLACE_KINDS:
            score = max(score, 0.93)
        if area_wish and pname in {normalize_name(a) for a in aliases_for(label)}:
            score = max(score, 0.96)
        # Hotels/restaurants/malls named after a landmark are not the landmark.
        lodgingish = any(tok in pname for tok in _TENANT_NAME_TOKENS)
        if lodgingish and not wikidata_match(p, label):
            score *= 0.5
        if p.category in {"cafe", "restaurant", "bar"} and not wikidata_match(p, label):
            score *= 0.5
        if any(t in pname for t in ("itfaiye", "fire station", "police", "istasyon", "parking")):
            score *= 0.45
        # Soft distance penalty beyond 12 km — keep strong name/Wikidata hits alive
        # for metro-scale landmarks (Dubai Marina ≈19 km from Downtown).
        if dist > 12_000 and score < 0.95:
            score *= max(0.7, 1.0 - (dist - 12_000) / 60_000)
        if score < MUST_SCORE_THRESHOLD:
            continue
        aliases = aliases_for(label)
        matched = next(
            (a for a in aliases if normalize_name(a) in normalize_name(p.name)),
            aliases[0] if aliases else label,
        )
        # Prefer compact titles; never boost museums for area wishes.
        compactness = 1.0 - min(0.15, max(0.0, (len(pname) - 12) * 0.005))
        if kind in _AREA_PLACE_KINDS:
            compactness += 0.05
        elif p.category == "museum" and not area_wish:
            compactness += 0.02
        ranked.append(
            RankedPlace(
                place=p,
                score=score * compactness,
                matched_alias=matched,
                distance_m=dist,
            )
        )
    ranked.sort(key=lambda r: (-r.score, r.distance_m, len(r.place.name)))
    return ranked


_MEMORIAL_RE = re.compile(
    r"памятник|мемориал|memorial|statue|monument|воинам|ульянов|ленин\w*",
    re.I,
)


def _is_memorial_like(place: Place) -> bool:
    blob = f"{place.name} {place.category} {place.description} {getattr(place, 'placeKind', '')}"
    return bool(_MEMORIAL_RE.search(blob))


def diversity_bucket(place: Place) -> str:
    """Coarse bucket so «главные места» are not three near-identical statues."""
    blob = f"{place.name} {place.category} {place.description} {getattr(place, 'placeKind', '')}".lower()
    if _is_memorial_like(place):
        return "memorial"
    if place.category in {"museum", "religious", "park", "viewpoint", "beach", "restaurant", "cafe", "bar"}:
        return place.category
    if any(t in blob for t in ("кремл", "kremlin", "цитадел", "fortress")):
        return "fortress"
    if any(t in blob for t in ("мечет", "mosque", "храм", "церков", "church", "cathedral")):
        return "religious"
    if any(t in blob for t in ("музей", "museum", "галере")):
        return "museum"
    if any(t in blob for t in ("парк", "park", "сквер", "сад", "garden", "набереж")):
        return "park"
    if any(t in blob for t in ("улиц", "street", "баумана", "bauman")):
        return "street"
    return "attraction"


def places_are_duplicate(a: Place, b: Place) -> bool:
    if a.placeId and a.placeId == b.placeId:
        return True
    if a.wikidataId and b.wikidataId and a.wikidataId == b.wikidataId:
        return True
    na, nb = normalize_name(a.name), normalize_name(b.name)
    # Two Lenin / Ulyanov memorials are the same tourist beat even if far apart.
    if _is_memorial_like(a) and _is_memorial_like(b):
        ta, tb = _token_set(a.name), _token_set(b.name)
        person_stems = ("ленин", "ульянов", "lenin", "ulyanov")

        def _mentions_person(tokens: set[str]) -> bool:
            return any(
                t.startswith(stem) or stem.startswith(t)
                for t in tokens
                for stem in person_stems
            )

        if _mentions_person(ta) and _mentions_person(tb):
            return True
    if haversine_m(a.lat, a.lon, b.lat, b.lon) <= DEDUP_METERS:
        if na and nb and (na == nb or na in nb or nb in na):
            return True
        ta, tb = _token_set(a.name), _token_set(b.name)
        if ta and tb and len(ta & tb) / max(len(ta | tb), 1) >= 0.7:
            return True
    return False


# City → landmark search queries for generic «главные места» (still resolved via Places API).
CITY_LANDMARK_QUERIES: dict[str, list[str]] = {
    "казань": ["Казанский кремль", "Мечеть Кул-Шариф", "улица Баумана", "Набережная Казанки"],
    "kazan": ["Kazan Kremlin", "Kul Sharif Mosque", "Bauman Street"],
    "стамбул": ["Ayasofya", "Sultanahmet Camii", "Topkapı Palace", "Galata Tower"],
    "istanbul": ["Hagia Sophia", "Blue Mosque", "Topkapi Palace", "Galata Tower"],
    "анталья": ["Kaleiçi", "Hadrian Gate", "Antalya Museum"],
    "antalya": ["Kaleici", "Hadrian's Gate", "Antalya Museum"],
}


def diversify_places(places: list[Place], *, limit: int, already: list[Place] | None = None) -> list[Place]:
    """Pick up to `limit` places with distinct diversity buckets; cap memorials at 1."""
    prior = list(already or [])
    taken = {diversity_bucket(p) for p in prior}
    memorials = sum(1 for p in prior if diversity_bucket(p) == "memorial")
    # Prefer non-memorial landmarks first for «главные места».
    ranked = sorted(places, key=lambda p: (diversity_bucket(p) == "memorial", len(p.name)))
    out: list[Place] = []
    for p in ranked:
        if any(places_are_duplicate(p, q) for q in (*prior, *out)):
            continue
        bucket = diversity_bucket(p)
        if bucket == "memorial" and memorials >= 1:
            continue
        if bucket in taken and bucket not in {"attraction"}:
            continue
        out.append(p)
        taken.add(bucket)
        if bucket == "memorial":
            memorials += 1
        if len(out) >= limit:
            break
    # If still short (batch was all memorials), fill remaining with unused non-dupes.
    if len(out) < limit:
        for p in ranked:
            if len(out) >= limit:
                break
            if any(places_are_duplicate(p, q) for q in (*prior, *out)):
                continue
            if diversity_bucket(p) == "memorial" and memorials >= 1:
                continue
            out.append(p)
            if diversity_bucket(p) == "memorial":
                memorials += 1
    return out


def dedupe_places(places: list[Place]) -> list[Place]:
    out: list[Place] = []
    for p in places:
        if any(places_are_duplicate(p, q) for q in out):
            continue
        out.append(p)
    return out


def place_covers_named_wish(place: Place, wish: WishItem) -> bool:
    label = wish.label or wish.query
    if wish_targets_area(label) and _is_tenant_of_named_area(place, label):
        return False
    if wikidata_match(place, label):
        return True
    return name_match_score(place.name, label, [wish.query or ""]) >= MUST_SCORE_THRESHOLD
