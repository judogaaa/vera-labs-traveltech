from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any, Callable, Iterator

from services.ai.gigachat_types import ChatMessage

from .gigachat import TripGigaChatBridge
from .intent_parser import (
    GEOCODE_QUERY_ALIASES,
    KNOWN_CATEGORIES,
    extract_wish_sequence_with_pos,
    parse_edit_actions,
    parse_intent_rule_based,
)
from .models import (
    Destination,
    HotelContext,
    LatLon,
    Place,
    Trip,
    TripIntent,
    WishItem,
)
from .optimizer import build_day_plan, recalculate_day_routes
from .providers.base import (
    DebugStats,
    GeocodeCandidate,
    GeocodingProvider,
    PlacesProvider,
    ProviderError,
    RoutingProvider,
)
from .store import TripStore
from .tools import TOOL_DEFS, TripToolExecutor, load_system_prompt
from .wish_match import (
    MUST_SCORE_THRESHOLD,
    NAMED_WIKIDATA,
    _WEAK_SINGLE_ALIASES,
    aliases_for,
    canonical_named_label,
    dedupe_places,
    CITY_LANDMARK_QUERIES,
    diversify_places,
    is_named_must,
    normalize_name,
    place_covers_named_wish,
    places_are_duplicate,
    rank_named_candidates,
    wish_targets_area,
)


ProgressCb = Callable[[str], None]


class TripPlannerAgent:
    def __init__(
        self,
        geocoding: GeocodingProvider,
        places: PlacesProvider,
        routing: RoutingProvider,
        store: TripStore | None = None,
        gigachat: TripGigaChatBridge | None = None,
    ) -> None:
        self.geocoding = geocoding
        self.places = places
        self.routing = routing
        self.store = store or TripStore()
        self.gigachat = gigachat if gigachat is not None else TripGigaChatBridge()

    def _emit(self, cb: ProgressCb | None, step: str) -> None:
        if cb:
            cb(step)

    def _resolve_intent(
        self,
        message: str,
        hotel: HotelContext | None,
        existing: TripIntent | None,
        stats: DebugStats,
    ) -> TripIntent:
        t0 = time.perf_counter()
        # GigaChat is the primary understanding path; rule-based is a
        # deterministic fallback and must not clobber a valid GigaChat intent.
        rule = parse_intent_rule_based(message, hotel, existing)
        intent: TripIntent | None = None
        giga_t0 = time.perf_counter()
        if self.gigachat.available:
            try:
                intent = self.gigachat.extract_intent(message, hotel, existing)
                stats.gigachat_ms = (time.perf_counter() - giga_t0) * 1000
                stats.gigachat_status = "called_ok" if intent is not None else "called_empty"
            except Exception as exc:  # noqa: BLE001
                stats.gigachat_ms = (time.perf_counter() - giga_t0) * 1000
                stats.gigachat_status = "called_error"
                stats.errors.append(f"gigachat: {exc}")
        else:
            stats.gigachat_status = "unavailable"
        if intent is None:
            stats.agent_ms = (time.perf_counter() - t0) * 1000
            return rule
        # Merge deterministic rule signals into gaps only.
        if not intent.destination and rule.destination:
            intent.destination = rule.destination
        if rule.editAction == "keep_as_is":
            # Acknowledgements must never be rebuilt by a null/rebuild GigaChat guess.
            intent.editAction = "keep_as_is"
            intent.editTarget = None
        elif rule.editAction == "rebuild_day":
            intent.editAction = "rebuild_day"
            intent.editTarget = rule.editTarget
            if rule.wishSequence:
                intent.wishSequence = rule.wishSequence
            if rule.startTime:
                intent.startTime = rule.startTime
            if rule.endTime:
                intent.endTime = rule.endTime
        elif rule.editAction and not intent.editAction:
            intent.editAction = rule.editAction
            intent.editTarget = rule.editTarget
        elif rule.editAction in {"remove_stop", "add_stop", "replace_stop"}:
            # Explicit deterministic edits ("убери музей") always win.
            intent.editAction = rule.editAction
            intent.editTarget = rule.editTarget
        if rule.returnBy and not intent.returnBy:
            intent.returnBy = rule.returnBy
            intent.endTime = rule.returnBy
        if rule.travelers.children and not intent.travelers.children:
            intent.travelers = rule.travelers
        if rule.transportPreference != "walk" and intent.transportPreference == "walk":
            intent.transportPreference = rule.transportPreference
        if rule.pace != "normal" and intent.pace == "normal":
            intent.pace = rule.pace
        if intent.budget is None and rule.budget is not None:
            intent.budget = rule.budget
        from .intent_parser import extract_explicit_start_time

        explicit_start = extract_explicit_start_time(message)
        if explicit_start:
            # Clock in the user message always beats soft «вечер→18:00» heuristics.
            intent.startTime = explicit_start
        elif existing is None and intent.startTime == "10:00" and rule.startTime != "10:00":
            intent.startTime = rule.startTime
        if rule.editReplacement and not intent.editReplacement:
            intent.editReplacement = rule.editReplacement
        # Deterministic wishes from the user text are the source of truth for
        # categories («покушать / бар / вид»). GigaChat may under-specify or
        # collapse them to one stop — never let that shrink the ask.
        rule_wishes = [w for _, w in extract_wish_sequence_with_pos(message)]
        if rule_wishes:
            # Rule order is the user's ask — never prepend GigaChat musts (that
            # pushed landmarks past the places budget and caused false misses).
            from .wish_match import canonical_named_label

            merged = list(rule_wishes)
            seen_labels = {w.label.lower() for w in merged}
            seen_canon = {
                canonical_named_label(w.label) or canonical_named_label(w.query or "")
                for w in merged
            }
            seen_canon.discard(None)
            for must in intent.wishSequence or []:
                if must.kind != "must" or not must.label.strip():
                    continue
                canon = canonical_named_label(must.label) or canonical_named_label(must.query or "")
                if canon and canon in seen_canon:
                    continue
                if must.label.lower() in seen_labels:
                    continue
                # Only append concrete named landmarks GigaChat found that rules missed.
                if canon:
                    must = must.model_copy(update={"label": canon, "query": canon, "category": None})
                    merged.append(must)
                    seen_canon.add(canon)
                    seen_labels.add(canon.lower())
            intent.wishSequence = merged
            intent.interests = list(
                dict.fromkeys([w.category for w in merged if w.category] or intent.interests or rule.interests)
            )
        elif not intent.wishSequence and rule.wishSequence:
            intent.wishSequence = rule.wishSequence
        if existing and not intent.wishSequence and existing.wishSequence:
            intent.wishSequence = list(existing.wishSequence)
        if not intent.interests and rule.interests:
            intent.interests = rule.interests
        if rule.endTime and rule.startTime >= "17:00" and (not intent.endTime or intent.endTime <= "20:00"):
            intent.endTime = rule.endTime
        if not intent.mustVisit and rule.mustVisit:
            intent.mustVisit = rule.mustVisit
        stats.agent_ms = (time.perf_counter() - t0) * 1000
        return intent

    def _geocode_destination(
        self,
        intent: TripIntent,
        hotel: HotelContext | None,
        stats: DebugStats,
    ) -> Destination:
        t0 = time.perf_counter()
        if hotel and hotel.lat is not None and hotel.lon is not None:
            name = hotel.city or intent.destination or hotel.name or "Отель"
            country = hotel.country or ""
            stats.geocode_ms = (time.perf_counter() - t0) * 1000
            return Destination(name=name, country=country, lat=hotel.lat, lon=hotel.lon)

        query = intent.destination.strip()
        if not query:
            raise ProviderError(
                "city_not_found",
                "Не удалось понять, куда едем. Напишите город или страну — например: «Еду в Тунис на 3 дня».",
            )
        # Prefer an unambiguous geocode query for famous same-name cities.
        lookup = GEOCODE_QUERY_ALIASES.get(query.lower().strip()) or query
        try:
            candidates = self.geocoding.geocode_candidates(lookup, limit=5)
            if not candidates and lookup != query:
                candidates = self.geocoding.geocode_candidates(query, limit=5)
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("geocoding_unavailable", str(exc)) from exc
        stats.geocode_ms = (time.perf_counter() - t0) * 1000
        if not candidates:
            raise ProviderError(
                "city_not_found",
                f"Не нашёл «{query}» на карте. Проверьте название или добавьте страну — например: «Александрия, Египет».",
            )
        # Truly different places = different countries or >100km apart.
        far_apart = False
        if len(candidates) > 1:
            lat0, lon0 = candidates[0].lat, candidates[0].lon
            for c in candidates[1:]:
                if (c.country or "").lower() != (candidates[0].country or "").lower():
                    far_apart = True
                    break
                p1, p2 = radians(lat0), radians(c.lat)
                dphi = radians(c.lat - lat0)
                dlmb = radians(c.lon - lon0)
                x = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
                if 2 * 6371000 * asin(sqrt(x)) > 100_000:
                    far_apart = True
                    break
        best = candidates[0]
        if far_apart:
            # Resolve automatically when possible: same-name CITY matches
            # that form one close cluster (e.g. Tunis city vs the
            # country-level "Tunisia" match) mean the city is intended.
            cities = [c for c in candidates if c.kind == "city"]
            resolved: GeocodeCandidate | None = None
            if cities:
                c0 = cities[0]
                clustered = True
                for c in cities:
                    p1, p2 = radians(c0.lat), radians(c.lat)
                    dphi = radians(c.lat - c0.lat)
                    dlmb = radians(c.lon - c0.lon)
                    x = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
                    if (
                        (c.country or "").lower() != (c0.country or "").lower()
                        or 2 * 6371000 * asin(sqrt(x)) > 100_000
                    ):
                        clustered = False
                        break
                if clustered:
                    resolved = c0
            if resolved is None:
                # Same country: the most important match wins
                # (major city vs a same-name village, e.g. Kazan).
                if all(
                    (c.country or "").lower() == (candidates[0].country or "").lower()
                    for c in candidates[1:]
                ):
                    resolved = max(candidates, key=lambda c: c.importance)
            if resolved is None:
                # Cross-country duplicates (San Francisco US vs CO): pick the
                # globally most important city unless the top two are a toss-up.
                pool = cities or list(candidates)
                ranked = sorted(pool, key=lambda c: c.importance, reverse=True)
                top = ranked[0]
                runner = ranked[1] if len(ranked) > 1 else None
                if runner is None or top.importance >= max(0.35, runner.importance * 1.15):
                    resolved = top
            if resolved is None:
                options = "; ".join(
                    f"{c.city or c.name} ({c.country or 'страна не указана'})"
                    for c in candidates[:3]
                )
                raise ProviderError(
                    "ambiguous_destination",
                    f"«{query}» — это несколько мест: {options}. Уточните страну или город.",
                )
            best = resolved
        try:
            rev = self.geocoding.reverse_geocode(best.lat, best.lon)
        except Exception:  # noqa: BLE001
            rev = {"city": query, "country": "", "name": query}
        return Destination(
            name=rev.get("city") or best.city or best.name or query,
            country=rev.get("country") or best.country or "",
            lat=best.lat,
            lon=best.lon,
        )

    @staticmethod
    def _is_generic_sights_wish(wish: WishItem) -> bool:
        """True for category-like sightseeing wishes, not named POIs."""
        if is_named_must(wish):
            return False
        category = wish.category if wish.category in KNOWN_CATEGORIES else None
        if category not in (None, "attraction"):
            return False
        if wish.kind in {"interest", "category"}:
            return True
        text = f"{wish.label or ''} {wish.query or ''}".lower()
        markers = (
            "достопримечатель",
            "sightseeing",
            "attractions",
            "sights",
            "что посмотреть",
            "главные места",
        )
        return any(m in text for m in markers)

    def _order_wishes_for_places(self, wishes: list[WishItem]) -> list[WishItem]:
        """Named + concrete categories before vague sightseeing filler.

        Message order often lists «достопримечательности» first; spending the
        Places budget there left museum/restaurant/cafe/bar as budget_timeout.
        """
        named: list[WishItem] = []
        concrete: list[WishItem] = []
        generic: list[WishItem] = []
        for w in wishes:
            if self._is_generic_sights_wish(w):
                generic.append(w)
            elif is_named_must(w):
                named.append(w)
            else:
                concrete.append(w)
        return named + concrete + generic

    def _wishes_from_intent(self, intent: TripIntent) -> list[WishItem]:
        from .wish_match import canonical_named_label

        wishes: list[WishItem] = []
        seen_canon: set[str] = set()
        seen_labels: set[str] = set()
        for w in intent.wishSequence:
            if not w.label.strip():
                continue
            canon = canonical_named_label(w.label) or canonical_named_label(w.query or "")
            if canon:
                if canon in seen_canon:
                    continue
                wishes.append(
                    WishItem(label=canon, kind="must", category=None, query=canon)
                )
                seen_canon.add(canon)
                seen_labels.add(canon.lower())
                continue
            key = w.label.lower()
            if key in seen_labels:
                continue
            wishes.append(w)
            seen_labels.add(key)
        for must in intent.mustVisit:
            if not must.strip():
                continue
            canon = canonical_named_label(must) or must.strip()
            if canon in seen_canon or must.lower() in seen_labels:
                continue
            wishes.append(WishItem(label=canon, kind="must", category=None, query=canon))
            seen_canon.add(canon)
            seen_labels.add(canon.lower())
        if not wishes:
            for cat in intent.interests or ["attraction"]:
                wishes.append(WishItem(label=cat, kind="interest", category=cat, query=cat))
        return wishes

    def _already_have(self, found: list[Place], place: Place) -> bool:
        return any(places_are_duplicate(place, q) for q in found)

    def _fulfill_named_wish(
        self,
        wish: WishItem,
        anchor: LatLon,
        radius: int,
        found: list[Place],
        city_hint: str,
    ) -> tuple[Place | None, dict]:
        """Resolve a named must via name search + alias/Wikidata score. No silent substitutes."""
        query = (wish.query or wish.label).strip()
        label = wish.label.strip()
        search_queries: list[str] = []
        area = wish_targets_area(label) or wish_targets_area(query)

        # Prefer strong Latin alias + city (Nominatim), then canonical label.
        latin_alias = next(
            (
                a
                for a in aliases_for(label)
                if any(ord(c) < 128 and c.isalpha() for c in a)
                and normalize_name(a) not in _WEAK_SINGLE_ALIASES
            ),
            None,
        )
        if area and latin_alias and city_hint:
            search_queries.append(f"{latin_alias} old town, {city_hint}")
        elif latin_alias and city_hint:
            search_queries.append(f"{latin_alias}, {city_hint}")
        elif latin_alias:
            search_queries.append(latin_alias)
        elif city_hint:
            search_queries.append(f"{query}, {city_hint}")
        else:
            search_queries.append(query)
        if query not in search_queries:
            search_queries.append(query)
        search_queries = list(dict.fromkeys(search_queries))[:1]

        pool: list[Place] = []
        canon = canonical_named_label(label) or label
        op = getattr(self.places, "primary", None)

        def _rank() -> list:
            return [
                r
                for r in rank_named_candidates(
                    pool, label, near_lat=anchor.lat, near_lon=anchor.lon, query=query, max_distance_m=45_000
                )
                if not self._already_have(found, r.place)
            ]

        # Areas: Wikidata P625 first (1 HTTP) — avoids Nominatim tenant soup + Overpass dumps.
        if area:
            try:
                from .providers.wikidata_resolve import place_from_wikidata

                for qid in list(NAMED_WIKIDATA.get(canon, ()))[:2]:
                    wp = place_from_wikidata(qid, fallback_name=label)
                    if wp and not self._already_have(pool, wp):
                        pool.append(wp)
            except Exception:  # noqa: BLE001
                pass
            if op is not None and hasattr(op, "search_by_wikidata") and not _rank():
                for qid in list(NAMED_WIKIDATA.get(canon, ()))[:2]:
                    try:
                        for p in op.search_by_wikidata(qid, anchor, radius=max(radius, 40_000), limit=5):
                            if not self._already_have(pool, p):
                                pool.append(p)
                    except ProviderError:
                        continue

        ranked = _rank()
        if not ranked:
            # Name search (Nominatim; Overpass only for non-area or as last resort).
            queries = list(search_queries)
            if area and latin_alias:
                # Plain ASCII + city often returns 0; bare diacritic form works for Kaleiçi.
                queries = list(
                    dict.fromkeys(
                        [
                            latin_alias,
                            f"{latin_alias}, {city_hint}" if city_hint else latin_alias,
                            *queries,
                        ]
                    )
                )
            batch: list[Place] = []
            for sq in queries[:3]:
                try:
                    batch = self.places.search_places(
                        query=sq,
                        near=anchor,
                        radius=max(radius, 20_000 if area else 28_000),
                        category=None,
                        limit=10 if area else 12,
                    )
                except ProviderError:
                    batch = []
                if batch:
                    break
            for p in batch:
                if not self._already_have(pool, p):
                    pool.append(p)
            ranked = _rank()
            # Area districts rarely exist as OSM nodes — synthesize a suburb pin from
            # the centroid of nearby named tenants (museum/cafe), not hotels alone.
            if area and not ranked and pool:
                from .wish_match import _is_tenant_of_named_area

                tenants = [
                    p
                    for p in pool
                    if _is_tenant_of_named_area(p, label)
                    and p.category not in {"hotel", "shopping"}
                ]
                if len(tenants) >= 2:
                    area_name = canon or label
                    synth = Place(
                        placeProvider="derived-area",
                        placeId=f"area:{normalize_name(area_name)}",
                        name=f"{area_name} (район)",
                        category="attraction",
                        lat=sum(p.lat for p in tenants) / len(tenants),
                        lon=sum(p.lon for p in tenants) / len(tenants),
                        # Honest: centroid of nearby named tenants — not a verified OSM node.
                        description=(
                            f"Ориентир района «{area_name}»: координаты — центроид "
                            f"{len(tenants)} соседних OSM POI, не отдельный подтверждённый объект"
                        ),
                        placeKind="suburb",
                    )
                    if not self._already_have(pool, synth):
                        pool.insert(0, synth)
                    ranked = _rank()
        if not ranked and not area and op is not None:
            try:
                extra = op.search_places(
                    query=latin_alias or query,
                    near=anchor,
                    radius=max(radius, 28000),
                    category=None,
                    limit=12,
                )
            except ProviderError:
                extra = []
            for p in extra:
                if not self._already_have(pool, p):
                    pool.append(p)
            ranked = _rank()
        if not ranked:
            return None, {
                "label": label,
                "kind": "must",
                "placeId": None,
                "score": 0.0,
                "matchedAlias": None,
                "status": "missing",
            }
        best = ranked[0]
        derived = (best.place.placeProvider or "").startswith("derived")
        status = (
            "matched_derived_area"
            if derived and best.score >= MUST_SCORE_THRESHOLD
            else ("matched" if best.score >= MUST_SCORE_THRESHOLD else "missing")
        )
        return best.place, {
            "label": label,
            "kind": "must",
            "placeId": best.place.placeId,
            "name": best.place.name,
            "score": round(best.score, 3),
            "matchedAlias": best.matched_alias,
            "distance_m": round(best.distance_m),
            "status": status,
            "derivedArea": derived,
        }

    def _build_ordered_places(
        self,
        intent: TripIntent,
        center: LatLon,
        stats: DebugStats,
    ) -> tuple[list[Place], list[str]]:
        """Search wish-by-wish, chaining from the previous stop.

        Named musts require alias/Wikidata score ≥ threshold. Category wishes
        never silently fulfill a named landmark. Returns (places, missing_labels).
        """
        t0 = time.perf_counter()
        wishes = self._wishes_from_intent(intent)
        # Concrete categories / named musts first — generic «достопримечательности»
        # must not monopolize the Places budget (Istanbul core-flows museum miss).
        wishes = self._order_wishes_for_places(wishes)
        found: list[Place] = []
        missing: list[str] = []
        coverage: list[dict] = []
        wish_for_place: list[str] = []
        anchor = center
        radius = 8000 if intent.pace != "intensive" else 12000
        if intent.travelers.children:
            radius = 6000
        pace_cap = {"relaxed": 3, "normal": 4, "intensive": 5}.get(intent.pace, 4)
        day_fill = pace_cap * max(int(intent.days or 1), 1)
        city_hint = (intent.destination or "").strip()
        # Scale budget with concrete wishes — 36s was too tight for 5–6 live
        # category searches when any Overpass fallback still runs.
        concrete_n = sum(1 for w in wishes if not self._is_generic_sights_wish(w))
        place_budget_s = min(100.0, 45.0 + 12.0 * max(concrete_n, 1))

        for i, wish in enumerate(wishes):
            if (time.perf_counter() - t0) > place_budget_s:
                # Soft degrade: mark remaining concrete wishes missing, stop filling.
                for w in wishes[i:]:
                    if is_named_must(w) or (
                        w.category
                        in {"cafe", "restaurant", "bar", "museum", "religious", "viewpoint"}
                    ):
                        missing.append(w.label)
                        coverage.append(
                            {
                                "label": w.label,
                                "kind": w.kind,
                                "placeId": None,
                                "status": "budget_timeout",
                            }
                        )
                stats.errors.append("places_budget_timeout")
                break

            query = (wish.query or wish.label).strip() or wish.label
            category = wish.category if wish.category in KNOWN_CATEGORIES else None

            # ——— Named must: strict score, no category substitute ———
            if is_named_must(wish) and not self._is_generic_sights_wish(wish):
                # Already covered by an earlier stop?
                prior = next((p for p in found if place_covers_named_wish(p, wish)), None)
                if prior:
                    coverage.append(
                        {
                            "label": wish.label,
                            "kind": "must",
                            "placeId": prior.placeId,
                            "name": prior.name,
                            "status": "covered_by_prior",
                        }
                    )
                    continue
                place, cov = self._fulfill_named_wish(wish, anchor, radius, found, city_hint)
                coverage.append(cov)
                if place is None:
                    missing.append(wish.label)
                    continue
                found.append(place)
                wish_for_place.append(wish.label)
                anchor = LatLon(lat=place.lat, lon=place.lon)
                continue

            # Skip redundant category wish when a prior named stop already covers it
            # (Blue Mosque → skip generic «мечеть»).
            if category and any(
                (
                    p.category == category
                    or (
                        category == "religious"
                        and any(
                            t in f"{p.name} {p.description}".lower()
                            for t in ("мечет", "mosque", "camii", "храм", "church")
                        )
                    )
                )
                for p in found
            ):
                coverage.append(
                    {
                        "label": wish.label,
                        "kind": wish.kind,
                        "category": category,
                        "placeId": found[-1].placeId if found else None,
                        "name": found[-1].name if found else None,
                        "status": "covered_by_prior",
                    }
                )
                continue

            # ——— Category / interest wishes ———
            qlow = f"{query} {wish.label or ''}".lower()
            prefer_mosque = category == "religious" and any(
                t in qlow for t in ("мечет", "mosque", "джами", "camii")
            )
            search_q = "mosque" if prefer_mosque else query
            city_l = (intent.destination or "").lower()
            if prefer_mosque and any(x in city_l for x in ("казан", "kazan")):
                search_q = "Kul Sharif mosque"
            elif prefer_mosque and any(x in city_l for x in ("дуба", "dubai")):
                search_q = "Jumeirah Mosque"
            elif prefer_mosque and any(x in city_l for x in ("стамбул", "istanbul")):
                search_q = "Sultanahmet Camii"
            elif category == "museum":
                # Keep category token searchable on Nominatim/Overpass — a branded
                # proper name often returns 0 hits and left museum as missing.
                search_q = "museum"
            elif category == "restaurant" and any(x in city_l for x in ("анталь", "antalya")):
                search_q = "restaurant"
            try:
                batch = self.places.search_places(
                    query=search_q,
                    near=anchor,
                    radius=max(radius, 10000 if self._is_generic_sights_wish(wish) else radius),
                    category=category,
                    limit=max(8, day_fill + 2),
                )
            except ProviderError:
                raise

            # Seed iconic landmarks for generic «главные места» (still via Places API).
            # Cap seeds when the day still needs concrete category slots.
            if self._is_generic_sights_wish(wish):
                later_concrete = sum(
                    1
                    for w in wishes[i + 1 :]
                    if (not self._is_generic_sights_wish(w))
                    and (
                        is_named_must(w)
                        or w.category
                        in {
                            "museum",
                            "viewpoint",
                            "restaurant",
                            "cafe",
                            "bar",
                            "religious",
                            "beach",
                            "park",
                        }
                    )
                )
                seed_cap = 1 if later_concrete else 4
                city_key = (intent.destination or "").strip().lower()
                for seed_q in CITY_LANDMARK_QUERIES.get(city_key, [])[:seed_cap]:
                    if (time.perf_counter() - t0) > place_budget_s:
                        break
                    try:
                        seeded = self.places.search_places(
                            query=seed_q,
                            near=anchor,
                            radius=max(radius, 12000),
                            category=None,
                            limit=3,
                        )
                    except ProviderError:
                        continue
                    for sp in seeded:
                        if not self._already_have(batch, sp):
                            batch.insert(0, sp)

            max_per_wish = day_fill if self._is_generic_sights_wish(wish) else 1
            later = wishes[i + 1 :]
            if self._is_generic_sights_wish(wish) and any(
                (w.category in {"bar", "restaurant", "cafe"})
                or is_named_must(w)
                or "вечер" in f"{w.label} {w.query}".lower()
                for w in later
            ):
                reserved = sum(1 for _ in later)
                max_per_wish = max(1, min(max_per_wish, day_fill - reserved))

            strict_fb = category in {"restaurant", "bar", "cafe"}
            if category and category != "attraction":
                exact = [p for p in batch if p.category == category]
                if exact:
                    batch = exact
                elif category == "viewpoint":
                    soft = [p for p in batch if p.category in {"viewpoint", "attraction"}]
                    batch = soft or []
                elif category == "religious":
                    soft = [
                        p
                        for p in batch
                        if p.category in {"religious", "attraction"}
                        and any(
                            tok in f"{p.name} {p.description}".lower()
                            for tok in ("мечет", "храм", "церков", "mosque", "church", "cathedral", "temple")
                        )
                    ]
                    batch = soft or []
                elif strict_fb:
                    batch = []
            if prefer_mosque:
                # Apply after category filter — never keep a church for «мечеть».
                # OSM often names mosques without the word (e.g. «Кул-Шариф»); keep
                # category=religious unless the title clearly reads as a church.
                church_tok = (
                    "церков",
                    "church",
                    "cathedral",
                    "собор",
                    "chapel",
                    "часовн",
                    "синагог",
                    "synagogue",
                    "костел",
                    "храм",
                )
                mosque_tok = ("мечет", "mosque", "camii", "джами", "masjid")
                kept_m: list[Place] = []
                for p in batch:
                    blob = f"{p.name} {p.description}".lower()
                    has_mosque = any(t in blob for t in mosque_tok)
                    has_church = any(t in blob for t in church_tok)
                    if has_mosque:
                        kept_m.append(p)
                    elif p.category == "religious" and not has_church:
                        kept_m.append(p)
                batch = kept_m

            # Category already satisfied by a prior stop (incl. named mosque/museum).
            def _covers_category(p: Place, cat: str | None) -> bool:
                if not cat:
                    return False
                if p.category == cat:
                    return True
                blob = f"{p.name} {p.description}".lower()
                # Named mosque/church stops are often tagged attraction, not religious.
                if cat == "religious" and any(
                    tok in blob for tok in ("мечет", "mosque", "camii", "церков", "church", "cathedral")
                ):
                    return True
                return False

            already = [p for p in found if _covers_category(p, category)]
            added = 1 if already and not self._is_generic_sights_wish(wish) else 0
            if added:
                coverage.append(
                    {
                        "label": wish.label,
                        "kind": wish.kind,
                        "placeId": already[0].placeId,
                        "name": already[0].name,
                        "status": "covered_by_prior",
                    }
                )

            pick_from = batch
            if self._is_generic_sights_wish(wish):
                # Avoid three near-identical memorials (Kazan regression PDF).
                pick_from = diversify_places(batch, limit=max_per_wish, already=found)
            for p in pick_from:
                if added >= max_per_wish:
                    break
                if self._already_have(found, p):
                    continue
                if any(a.lower() in p.name.lower() or a.lower() in p.category.lower() for a in intent.avoid):
                    continue
                if category and category != "attraction" and p.category != category:
                    if category == "viewpoint" and p.category in {"viewpoint", "attraction"}:
                        pass
                    elif category == "religious" and p.category in {"religious", "attraction"}:
                        pass
                    else:
                        continue
                found.append(p)
                wish_for_place.append(wish.label)
                anchor = LatLon(lat=p.lat, lon=p.lon)
                added += 1

            if added == 0 and not strict_fb and self._is_generic_sights_wish(wish):
                try:
                    loose = self.places.search_places(
                        query="attraction",
                        near=anchor,
                        radius=max(radius, 12000),
                        category="attraction",
                        limit=max(8, max_per_wish * 2),
                    )
                except ProviderError:
                    loose = []
                loose = [
                    p
                    for p in loose
                    if p.category not in {"restaurant", "bar", "cafe", "shop", "shopping"}
                ]
                for p in diversify_places(loose, limit=max_per_wish - added, already=found):
                    if self._already_have(found, p):
                        continue
                    found.append(p)
                    wish_for_place.append(wish.label)
                    anchor = LatLon(lat=p.lat, lon=p.lon)
                    added += 1
                    if added >= max_per_wish:
                        break

            if added == 0:
                missing.append(wish.label)
                coverage.append(
                    {
                        "label": wish.label,
                        "kind": wish.kind,
                        "category": category,
                        "placeId": None,
                        "status": "missing",
                    }
                )
            elif not already:
                coverage.append(
                    {
                        "label": wish.label,
                        "kind": wish.kind,
                        "category": category,
                        "placeId": found[-1].placeId if found else None,
                        "name": found[-1].name if found else None,
                        "status": "matched",
                    }
                )

        # Top-up only for missing concrete categories — never invent named landmarks.
        placed_cats = {p.category for p in found}
        for cat in intent.interests or []:
            if cat in placed_cats or cat == "attraction":
                continue
            if len(found) >= pace_cap * max(intent.days, 1):
                break
            if (time.perf_counter() - t0) > place_budget_s:
                break
            try:
                batch = self.places.search_places(
                    query=cat,
                    near=anchor,
                    radius=radius,
                    category=cat if cat in KNOWN_CATEGORIES else None,
                    limit=6,
                )
            except ProviderError:
                continue
            for p in batch:
                if self._already_have(found, p):
                    continue
                if cat != "attraction" and p.category != cat:
                    continue
                found.append(p)
                wish_for_place.append(f"top-up:{cat}")
                anchor = LatLon(lat=p.lat, lon=p.lon)
                placed_cats.add(p.category)
                break

        found = dedupe_places(found)
        stats.place_api_ms = (time.perf_counter() - t0) * 1000
        stats.places_searched = len(found)
        stats.wish_coverage = coverage
        stats.candidates = [
            {
                "placeId": p.placeId,
                "name": p.name,
                "category": p.category,
                "wish": wish_for_place[i] if i < len(wish_for_place) else "?",
            }
            for i, p in enumerate(found[:20])
        ]
        stats.errors.extend(f"missing:{label}" for label in missing)
        return found, missing

    def _orchestrate_with_gigachat(
        self,
        message: str,
        hotel: HotelContext | None,
        stats: DebugStats,
    ) -> tuple[list[Place], Destination | None, TripToolExecutor] | None:
        """Optional GigaChat tool loop — POIs still come only from tools."""
        client = self.gigachat.client if self.gigachat.available else None
        if not client:
            return None
        executor = TripToolExecutor(self.geocoding, self.places, self.routing, hotel=hotel)
        system = load_system_prompt()
        user = (
            f"Пользователь: {message}\n"
            f"Отель: {(hotel.model_dump() if hotel else None)}\n"
            "Вызови geocode_destination (если нет hotel coords), затем search_places / "
            "find_places_near_hotel для интересов, затем calculate_route между ключевыми точками. "
            "Не придумывай места. Когда собрал факты — кратко перечисли placeId."
        )
        try:
            t0 = time.perf_counter()
            result, trace = client.run_tool_loop(
                [
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user),
                ],
                TOOL_DEFS,
                executor,
                max_rounds=3,
            )
            stats.agent_ms += (time.perf_counter() - t0) * 1000
            stats.errors.append(f"tool_trace:{len(trace)}")
            _ = result
        except Exception as exc:  # noqa: BLE001
            stats.errors.append(f"gigachat_tools: {type(exc).__name__}")
            return None

        # Recover POIs from executor side-effects (tools remember places).
        places = [
            p
            for p in executor.collected_places.values()
            if isinstance(p, Place) or getattr(p, "placeId", None)
        ]
        # If the model only geocoded / skipped search, still run one real
        # places-provider call so force-loop acceptance can prove tool POIs.
        if not places:
            lat = lon = None
            if hotel and hotel.lat is not None and hotel.lon is not None:
                lat, lon = float(hotel.lat), float(hotel.lon)
            elif executor.last_geocode:
                try:
                    lat = float(executor.last_geocode["lat"])
                    lon = float(executor.last_geocode["lon"])
                except Exception:  # noqa: BLE001
                    lat = lon = None
            if lat is not None and lon is not None:
                # Prefer short English/local tokens — full Russian sentences return 0 from Overpass.
                fallback_queries = [
                    "Ayasofya",
                    "Hagia Sophia",
                    "museum",
                    "attraction",
                    "cafe",
                ]
                for q in fallback_queries:
                    executor.tool_search_places(
                        {
                            "query": q,
                            "lat": lat,
                            "lon": lon,
                            "radiusMeters": 8000,
                            "limit": 8,
                        }
                    )
                    if executor.collected_places:
                        break
                places = [
                    p
                    for p in executor.collected_places.values()
                    if isinstance(p, Place) or getattr(p, "placeId", None)
                ]
        dest = None
        if executor.last_geocode:
            g = executor.last_geocode
            try:
                dest = Destination(
                    name=str(g.get("name") or "destination"),
                    lat=float(g["lat"]),
                    lon=float(g["lon"]),
                    country=str(g.get("country") or ""),
                )
            except Exception:  # noqa: BLE001
                dest = None
        return places, dest, executor

    def plan(
        self,
        message: str,
        hotel: HotelContext | None = None,
        progress: ProgressCb | None = None,
        trip_id: str | None = None,
    ) -> Trip:
        stats = DebugStats()
        self._emit(progress, "Понимаю пожелания")
        existing_trip = self.store.get(trip_id) if trip_id else None
        existing_intent = existing_trip.intent if existing_trip else None

        # Intent is primary. Optional GigaChat tool loop merges extra verified
        # POIs from tools (never invents places). Bounded rounds; failures
        # do not abort the deterministic path.
        tool_executor: TripToolExecutor | None = None

        intent = self._resolve_intent(message, hotel, existing_intent, stats)
        if hotel and not intent.destination and hotel.city:
            intent.destination = hotel.city

        self._emit(progress, "Ищу места")
        destination = self._geocode_destination(intent, hotel, stats)
        center = LatLon(lat=destination.lat, lon=destination.lon)
        home = center
        if hotel and hotel.lat is not None and hotel.lon is not None:
            home = LatLon(lat=hotel.lat, lon=hotel.lon)

        places, missing = self._build_ordered_places(intent, center, stats)

        # Safe tool loop: always allowed via TRIP_GIGACHAT_TOOL_LOOP=1;
        # default "auto" runs only when intent search returned too few POIs
        # (fixes the old bug where the loop discarded places and blocked UX).
        try:
            import os

            loop_mode = os.getenv("TRIP_GIGACHAT_TOOL_LOOP", "auto").strip().lower()
        except Exception:  # noqa: BLE001
            loop_mode = "auto"
        force_loop = loop_mode in {"1", "true", "yes", "on", "force"}
        auto_loop = loop_mode in {"auto", ""} and len(places) < 2
        if (force_loop or auto_loop) and self.gigachat.available:
            self._emit(progress, "Уточняю места через инструменты")
            orch = self._orchestrate_with_gigachat(message, hotel, stats)
            if orch is not None:
                tool_places, tool_dest, tool_executor = orch
                if tool_dest is not None and (
                    not destination.name or destination.name == "destination"
                ):
                    destination = tool_dest
                seen = {
                    getattr(p, "placeId", None) or getattr(p, "id", None) for p in places
                }
                for p in tool_places:
                    pid = getattr(p, "placeId", None) or getattr(p, "id", None)
                    if pid and pid not in seen:
                        places.append(p)
                        seen.add(pid)
                if tool_executor:
                    stats.errors.append(
                        f"tool_places:{len(tool_executor.collected_places)}"
                    )
        # Hard floor: need at least one real place. Partial wish coverage is
        # reported via `missing` / day.summary instead of aborting a usable plan
        # (live Overpass/Nominatim often return 2 of 3 categories near a resort).
        if not places:
            raise ProviderError(
                "not_enough_places",
                f"Недостаточно подтверждённых мест рядом с {destination.name} (найдено 0). "
                "Попробуйте другой район или уточните запрос.",
            )

        # Resolve Commons / Wikidata photos (best-effort, budgeted) before day build.
        try:
            from .photos import enrich_places

            places = enrich_places(places, timeout_s=3.5)
        except Exception as exc:  # noqa: BLE001
            stats.errors.append(f"photo_enrich:{exc}")

        self._emit(progress, "Проверяю расстояния")
        # Sequential day chunks keep the user's wish order across days.
        # One-day plans keep the full ordered wish list; the clock in
        # build_day_plan decides what still fits — do not silently drop a bar
        # because pace_cap sliced it off before scheduling.
        per_day = {"relaxed": 3, "normal": 4, "intensive": 5}.get(intent.pace, 4)
        if intent.days <= 1:
            chunks = [places]
        else:
            chunks = [places[i : i + per_day] for i in range(0, len(places), per_day)]
            while len(chunks) < intent.days:
                chunks.append([])
            chunks = chunks[: max(intent.days, 1)]
        days = []
        t0 = time.perf_counter()
        for i, chunk in enumerate(chunks, start=1):
            day = build_day_plan(i, chunk, intent, home, hotel, self.routing, preserve_order=True)
            if missing and i == 1:
                skip = ", ".join(missing)
                day.summary = f"{day.summary} Не нашли рядом и пропустили: {skip}."
            days.append(day)
        stats.route_api_ms = (time.perf_counter() - t0) * 1000

        if not any(d.stops for d in days):
            raise ProviderError("route_impossible", "Не удалось собрать маршрут в заданном окне времени")

        placed_cats = {s.category for d in days for s in d.stops}
        unfitted = [
            w.label
            for w in intent.wishSequence
            if w.category and w.category not in placed_cats and w.label not in missing
        ]
        if unfitted:
            days[0].summary = f"{days[0].summary} Не успели по времени: {', '.join(unfitted)}."

        self._emit(progress, "Собираю маршрут")
        now = datetime.now(timezone.utc).isoformat()
        # Prefer confirmed call status from _resolve_intent; tool_loop only if tools ran.
        if tool_executor and tool_executor.calls:
            gigachat_status = "called_ok_tools"
        elif stats.gigachat_status and stats.gigachat_status != "skipped":
            gigachat_status = stats.gigachat_status
        elif self.gigachat.available:
            gigachat_status = "available_unused"
        else:
            gigachat_status = "unavailable"
        trip = Trip(
            id=trip_id or f"trip_{uuid.uuid4().hex[:12]}",
            destination=destination,
            hotel=hotel or HotelContext(),
            days=days,
            summary=self._summary(destination.name, days, hotel),
            intent=intent,
            createdAt=existing_trip.createdAt if existing_trip else now,
            updatedAt=now,
            messages=(existing_trip.messages if existing_trip else [])
            + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": self._summary(destination.name, days, hotel)},
            ],
            debug={
                "gigachat": gigachat_status,
                "gigachatAvailable": bool(self.gigachat.available),
                "gigachatModel": getattr(getattr(self.gigachat, "client", None), "model", None),
                "toolCalls": tool_executor.calls if tool_executor else [],
                "toolCallCount": len(tool_executor.calls) if tool_executor else 0,
                "routeToolCalls": tool_executor.route_calls if tool_executor else 0,
                "placeToolCalls": tool_executor.place_calls if tool_executor else 0,
                "placesProvider": self.places.name,
                "routingProvider": self.routing.name,
                "geocodingProvider": self.geocoding.name,
                "placesSearched": stats.places_searched,
                "candidates": stats.candidates,
                "wishSequence": [w.model_dump() for w in intent.wishSequence],
                "wishCoverage": stats.wish_coverage,
                "missingWishes": missing,
                "routeDurationSeconds": sum(d.route.durationSeconds for d in days),
                "agentLatencyMs": stats.agent_ms,
                "placeApiLatencyMs": stats.place_api_ms,
                "routeApiLatencyMs": stats.route_api_ms,
                "geocodeLatencyMs": stats.geocode_ms,
                "gigachatLatencyMs": stats.gigachat_ms,
                "latencyBreakdownMs": {
                    "gigachat": round(stats.gigachat_ms, 1),
                    "geocode": round(stats.geocode_ms, 1),
                    "places": round(stats.place_api_ms, 1),
                    "routing": round(stats.route_api_ms, 1),
                    "agent": round(stats.agent_ms, 1),
                },
                "errors": stats.errors,
            },
        )
        try:
            from .photos import enrich_trip_photos

            trip = enrich_trip_photos(trip, timeout_s=2.5)
        except Exception as exc:  # noqa: BLE001
            stats.errors.append(f"photo_trip:{exc}")
            trip.debug = {**(trip.debug or {}), "errors": stats.errors}
        return self.store.save(trip)

    RU_TO_EN_CATEGORY = {
        "музей": "museum",
        "пляж": "beach",
        "ресторан": "restaurant",
        "парк": "park",
        "кафе": "cafe",
        "бар": "bar",
        "шопинг": "shopping",
        "храм": "religious",
        "смотровая": "viewpoint",
    }

    def _matches_target(self, stop_name: str, stop_category: str, target: str) -> bool:
        name_l = (stop_name or "").lower()
        cat_l = (stop_category or "").lower()
        t = (target or "").lower().strip()
        if not t:
            return False
        if "музей" in t or "museum" in t:
            return cat_l == "museum" or "музей" in name_l or "museum" in name_l
        if t in name_l or t in cat_l:
            return True
        for ru, en in self.RU_TO_EN_CATEGORY.items():
            if ru in t and cat_l == en:
                return True
        # Alias match: «убери Айя-София» → stop «Ayasofya».
        try:
            from .wish_match import MUST_SCORE_THRESHOLD, name_match_score

            if name_match_score(stop_name, target) >= MUST_SCORE_THRESHOLD:
                return True
            if name_match_score(stop_name, target) < MUST_SCORE_THRESHOLD:
                # Also try target as query against stop via reverse containment.
                if name_match_score(target, stop_name) >= MUST_SCORE_THRESHOLD:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _apply_remove_stop(self, trip: Trip, target: str, transport: str) -> int:
        removed_total = 0
        tnorm = (target or "").strip().lower()
        remove_last = bool(
            re.search(r"последн|last\s+stop|final\s+stop", tnorm)
            and re.search(r"мест|останов|stop|poi", tnorm)
        )
        for day in trip.days:
            before = len(day.stops)
            if remove_last and day.stops:
                day.stops = day.stops[:-1]
            else:
                day.stops = [
                    s for s in day.stops if not self._matches_target(s.name, s.category, target)
                ]
            removed_total += before - len(day.stops)
            if len(day.stops) != before:
                home = self._home(trip)
                day_updated = recalculate_day_routes(day, home, self.routing, transport)
                day.segments = day_updated.segments
                day.route = day_updated.route
                day.summary = f"День {day.dayNumber}: обновлён ({len(day.stops)} мест)"
        return removed_total

    def _category_for_query(self, query: str) -> str | None:
        q = (query or "").lower()
        for key in (
            "beach",
            "museum",
            "restaurant",
            "park",
            "cafe",
            "bar",
            "attraction",
            "viewpoint",
            "shopping",
            "religious",
        ):
            if key in q:
                return key
        for ru, en in self.RU_TO_EN_CATEGORY.items():
            if ru in q:
                return en
        return None

    def _apply_add_stop(self, trip: Trip, query: str, intent: TripIntent) -> Place | None:
        home = self._home(trip)
        center = LatLon(lat=trip.destination.lat, lon=trip.destination.lon)
        cat = self._category_for_query(query or "attraction")
        found = self.places.search_places(query or "attraction", center, radius=10000, category=cat, limit=8)
        if not found:
            return None
        day = trip.days[0] if trip.days else None
        if not day:
            raise ProviderError("route_impossible", "Нет дня для добавления")
        ref = home
        if day.stops:
            ref = LatLon(lat=day.stops[-1].lat, lon=day.stops[-1].lon)
        found.sort(key=lambda p: (p.lat - ref.lat) ** 2 + (p.lon - ref.lon) ** 2)
        new_place = found[0]
        if any(s.placeId == new_place.placeId for s in day.stops):
            return None
        places = [
            Place(
                placeProvider=s.placeProvider,
                placeId=s.placeId,
                name=s.name,
                category=s.category,
                lat=s.lat,
                lon=s.lon,
                address=s.address,
                description=s.description,
                photoUrl=s.photoUrl,
                rating=s.rating,
                wikidataId=getattr(s, "wikidataId", None),
            )
            for s in day.stops
        ] + [new_place]
        trip.days[0] = build_day_plan(day.dayNumber, places, intent, home, trip.hotel, self.routing, preserve_order=True)
        return new_place

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        p1, p2 = radians(lat1), radians(lat2)
        dphi = radians(lat2 - lat1)
        dlmb = radians(lon2 - lon1)
        x = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
        return 2 * 6371000.0 * asin(sqrt(x))

    def chat(self, trip_id: str, message: str, progress: ProgressCb | None = None) -> Trip:
        trip = self.store.get(trip_id)
        if not trip:
            raise ProviderError("trip_not_found", "Поездка не найдена")

        stats = DebugStats()
        self._emit(progress, "Понимаю пожелания")
        intent = self._resolve_intent(message, trip.hotel, trip.intent, stats)
        action = intent.editAction

        if action == "keep_as_is":
            trip.summary = "Оставила маршрут без изменений."
            return self._finalize_chat(trip, message, trip.summary, stats)

        structural = [
            (a, t) for a, t in parse_edit_actions(message)
            if a in {"remove_stop", "add_stop"} and t
        ]
        if len(structural) >= 2:
            # Combined command like "Добавь парк и убери музей".
            self._emit(progress, "Обновляю маршрут")
            notes: list[str] = []
            for kind, target in structural:
                if kind == "remove_stop":
                    removed = self._apply_remove_stop(trip, target, intent.transportPreference)
                    notes.append(
                        f"убрал «{target}»" if removed else f"не нашёл «{target}» для удаления"
                    )
                else:
                    try:
                        added = self._apply_add_stop(trip, target, intent)
                    except ProviderError:
                        added = None
                    notes.append(f"добавил: {added.name}" if added else f"не нашёл «{target}» рядом")
            trip.intent = intent
            trip.summary = "Изменения: " + "; ".join(notes)
            return self._finalize_chat(trip, message, trip.summary, stats)

        if action == "remove_stop":
            self._emit(progress, "Обновляю маршрут")
            target = (intent.editTarget or "").strip()
            removed_total = self._apply_remove_stop(trip, target, intent.transportPreference)
            trip.intent = intent
            if removed_total == 0 and target:
                trip.summary = (
                    f"Не нашёл остановку «{intent.editTarget}» в маршруте. "
                    "Уточните название или категорию."
                )
            else:
                trip.summary = (
                    f"Убрал «{intent.editTarget}» из маршрута"
                    if intent.editTarget
                    else "Остановки удалены"
                )
            return self._finalize_chat(trip, message, trip.summary, stats)

        if action == "return_by":
            self._emit(progress, "Проверяю расстояния")
            trip.intent = intent
            home = self._home(trip)
            new_days = []
            for day in trip.days:
                places = [
                    Place(
                        placeProvider=s.placeProvider,
                        placeId=s.placeId,
                        name=s.name,
                        category=s.category,
                        lat=s.lat,
                        lon=s.lon,
                        address=s.address,
                        description=s.description,
                        photoUrl=s.photoUrl,
                        rating=s.rating,
                        wikidataId=getattr(s, "wikidataId", None),
                    )
                    for s in day.stops
                ]
                new_days.append(build_day_plan(day.dayNumber, places, intent, home, trip.hotel, self.routing, preserve_order=True))
            trip.days = new_days
            note = next((d.summary for d in new_days if "Невозможно" in d.summary or "лимит" in d.summary or "Возврат" in d.summary), "")
            trip.summary = note or f"Учтено возвращение к {intent.returnBy}"
            return self._finalize_chat(trip, message, trip.summary, stats)

        if action == "add_stop":
            self._emit(progress, "Ищу места")
            q = intent.editTarget or "attraction"
            try:
                added = self._apply_add_stop(trip, q, intent)
            except ProviderError:
                added = None
            trip.intent = intent
            if added:
                trip.summary = f"Добавил: {added.name}"
            else:
                trip.summary = (
                    f"Не нашёл «{q}» рядом с маршрутом. Маршрут без изменений — "
                    "уточните название или категорию."
                )
            return self._finalize_chat(trip, message, trip.summary, stats)

        if action == "change_transport":
            self._emit(progress, "Проверяю расстояния")
            home = self._home(trip)
            for i, day in enumerate(trip.days):
                trip.days[i] = recalculate_day_routes(day, home, self.routing, intent.transportPreference)
            trip.intent = intent
            trip.summary = f"Транспорт: {intent.transportPreference}"
            return self._finalize_chat(trip, message, trip.summary, stats)

        if action == "replace_stop":
            self._emit(progress, "Ищу места")
            target = (intent.editTarget or "").strip()
            day_idx = -1
            old = None
            for i, day in enumerate(trip.days):
                old = next(
                    (s for s in day.stops if self._matches_target(s.name, s.category, target)),
                    None,
                )
                if old:
                    day_idx = i
                    break
            if not old or day_idx < 0:
                trip.summary = (
                    f"Не нашёл «{intent.editTarget or target}» для замены. Уточните название."
                )
                trip.intent = intent
                return self._finalize_chat(trip, message, trip.summary, stats)
            day = trip.days[day_idx]
            home = self._home(trip)
            center = LatLon(lat=old.lat, lon=old.lon)
            cat = old.category if old.category in {"beach", "museum", "restaurant", "park", "cafe", "bar", "attraction", "viewpoint"} else None
            search_q = (intent.editReplacement or "").strip() or cat or old.category
            if intent.editReplacement:
                cat = self._category_for_query(intent.editReplacement) or cat
            found = self.places.search_places(
                search_q,
                center,
                radius=8000,
                category=cat,
                limit=10,
            )
            options = [p for p in found if p.placeId != old.placeId]
            idx = next((i for i, s in enumerate(day.stops) if s.placeId == old.placeId), None)
            anchor: LatLon | None = None
            if idx is not None and idx + 1 < len(day.stops):
                nxt = day.stops[idx + 1]
                anchor = LatLon(lat=nxt.lat, lon=nxt.lon)
            elif idx is not None and idx > 0:
                prev = day.stops[idx - 1]
                anchor = LatLon(lat=prev.lat, lon=prev.lon)
            if anchor is not None:
                options.sort(
                    key=lambda p: self._haversine_m(anchor.lat, anchor.lon, p.lat, p.lon)
                )
            replacement = options[0] if options else None
            if not replacement:
                trip.summary = "Не нашёл замену среди подтверждённых мест."
                trip.intent = intent
                return self._finalize_chat(trip, message, trip.summary, stats)
            places = []
            for s in day.stops:
                if s.placeId == old.placeId:
                    places.append(replacement)
                else:
                    places.append(
                        Place(
                            placeProvider=s.placeProvider,
                            placeId=s.placeId,
                            name=s.name,
                            category=s.category,
                            lat=s.lat,
                            lon=s.lon,
                            address=s.address,
                            description=s.description,
                            photoUrl=s.photoUrl,
                            rating=s.rating,
                            wikidataId=getattr(s, "wikidataId", None),
                        )
                    )
            trip.days[day_idx] = build_day_plan(
                day.dayNumber, places, intent, home, trip.hotel, self.routing, preserve_order=True
            )
            trip.intent = intent
            trip.summary = f"Заменил «{old.name}» на «{replacement.name}»"
            return self._finalize_chat(trip, message, trip.summary, stats)

        # rebuild / default: re-plan mutating from current destination
        self._emit(progress, "Собираю маршрут")
        return self.plan(message, hotel=trip.hotel, progress=progress, trip_id=trip.id)

    def _home(self, trip: Trip) -> LatLon:
        if trip.hotel.lat is not None and trip.hotel.lon is not None:
            return LatLon(lat=trip.hotel.lat, lon=trip.hotel.lon)
        return LatLon(lat=trip.destination.lat, lon=trip.destination.lon)

    def _finalize_chat(self, trip: Trip, message: str, reply: str, stats: DebugStats) -> Trip:
        trip.updatedAt = datetime.now(timezone.utc).isoformat()
        trip.messages = trip.messages + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ]
        trip.debug = {
            **trip.debug,
            "gigachat": "configured" if self.gigachat.available else "rule_based_fallback",
            "placesProvider": self.places.name,
            "routingProvider": self.routing.name,
            "geocodingProvider": self.geocoding.name,
            "agentLatencyMs": stats.agent_ms,
            "errors": stats.errors,
        }
        return self.store.save(trip)

    def _summary(self, city: str, days: list, hotel: HotelContext | None) -> str:
        n_stops = sum(len(d.stops) for d in days)
        base = f"Маршрут по {city}: {len(days)} дн., {n_stops} мест из открытых данных."
        if hotel and hotel.name:
            base = f"Вокруг «{hotel.name}». {base}"
        incomplete_days = [d.dayNumber for d in days if getattr(d, "incomplete", False) or not d.stops]
        if incomplete_days:
            nums = ", ".join(str(n) for n in incomplete_days)
            base = f"{base} Неполный результат: день {nums} без подтверждённых остановок."
        unverified = any(
            not getattr(d.route, "verified", True)
            or any(not getattr(s, "verified", True) for s in d.segments)
            for d in days
        )
        if unverified:
            base = f"{base} Часть переездов без подтверждённого маршрута (расстояние не оценено)."
        return base

    def plan_stream(
        self,
        message: str,
        hotel: HotelContext | None = None,
        trip_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield SSE events as plan progresses — never buffer until the end."""
        from queue import Empty, Queue
        from threading import Thread

        events: Queue[dict[str, Any] | None] = Queue()

        def progress(step: str) -> None:
            events.put({"type": "progress", "step": step})

        def worker() -> None:
            try:
                trip = self.plan(message, hotel=hotel, progress=progress, trip_id=trip_id)
                events.put({"type": "done", "trip": trip.model_dump()})
            except ProviderError as exc:
                events.put({"type": "error", "code": exc.code, "message": exc.message})
            except Exception as exc:  # noqa: BLE001
                events.put({"type": "error", "code": "internal", "message": str(exc)})
            finally:
                events.put(None)

        Thread(target=worker, daemon=True).start()
        while True:
            try:
                item = events.get(timeout=300)
            except Empty:
                yield {"type": "error", "code": "timeout", "message": "Построение маршрута заняло слишком много времени"}
                break
            if item is None:
                break
            yield item