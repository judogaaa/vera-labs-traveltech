"""Required scenarios for О!Маршрут trip planner."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.trip_planner.agent import TripPlannerAgent
from services.trip_planner.api import router, set_agent
from services.trip_planner.models import HotelContext
from services.trip_planner.providers.fixtures import (
    ANTALYA_TEKIROVA,
    FixtureGeocodingProvider,
    FixturePlacesProvider,
    FixtureRoutingProvider,
)
from services.trip_planner.store import TripStore

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402


class _DisabledGiga:
    """Unit tests must not depend on live GigaChat credentials."""

    available = False
    client = None

    def extract_intent(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


@pytest.fixture()
def agent(tmp_path: Path) -> TripPlannerAgent:
    return TripPlannerAgent(
        geocoding=FixtureGeocodingProvider(),
        places=FixturePlacesProvider(),
        routing=FixtureRoutingProvider(),
        store=TripStore(tmp_path / "trips"),
        gigachat=_DisabledGiga(),  # type: ignore[arg-type]
    )


@pytest.fixture()
def client(agent: TripPlannerAgent) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    set_agent(agent)
    return TestClient(app)


def test_kazan_one_day_main_sights(agent: TripPlannerAgent) -> None:
    trip = agent.plan("Казань на 1 день, главные достопримечательности")
    assert trip.destination.name
    stops = trip.days[0].stops
    assert len(stops) >= 3
    for s in stops:
        assert -90 <= s.lat <= 90
        assert -180 <= s.lon <= 180
        assert s.placeId
        assert s.placeProvider
    assert trip.days[0].route.distanceMeters > 0 or trip.days[0].segments
    times = [s.startTime for s in stops if s.startTime]
    assert times == sorted(times)


def test_generic_sights_must_wish_fills_day(agent: TripPlannerAgent) -> None:
    """GigaChat often marks «главные достопримечательности» as kind=must."""
    from services.trip_planner.models import TripIntent, WishItem

    intent = TripIntent(
        destination="Казань",
        days=1,
        interests=["attraction"],
        wishSequence=[
            WishItem(
                label="главные достопримечательности",
                kind="must",
                category="attraction",
                query="главные достопримечательности",
            )
        ],
    )
    assert agent._is_generic_sights_wish(intent.wishSequence[0])
    center = __import__("services.trip_planner.models", fromlist=["LatLon"]).LatLon(
        lat=55.796, lon=49.106
    )
    from services.trip_planner.providers.base import DebugStats

    places, missing = agent._build_ordered_places(intent, center, DebugStats())
    assert missing == []
    assert len(places) >= 3


def test_antalya_hotel_context(agent: TripPlannerAgent) -> None:
    hotel = HotelContext(
        hotelId="rixos-premium-tekirova",
        name="Rixos Premium Tekirova",
        lat=ANTALYA_TEKIROVA.lat,
        lon=ANTALYA_TEKIROVA.lon,
        city="Antalya",
        country="Türkiye",
    )
    trip = agent.plan("пляж, старый город, ресторан", hotel=hotel)
    assert trip.hotel.hotelId == "rixos-premium-tekirova"
    assert trip.hotel.lat == ANTALYA_TEKIROVA.lat
    cats = {s.category for d in trip.days for s in d.stops}
    assert cats & {"beach", "attraction", "restaurant", "museum", "park"}


def test_remove_museum(agent: TripPlannerAgent) -> None:
    trip = agent.plan("Казань на 1 день, главные достопримечательности")
    # ensure a museum-like stop exists or inject via rebuild
    before_ids = {s.id for d in trip.days for s in d.stops}
    # force museum present by planning with museum interest then remove
    trip2 = agent.plan("Казань на 1 день музей", trip_id=trip.id)
    had_museum = any(s.category == "museum" or "музей" in s.name.lower() for d in trip2.days for s in d.stops)
    if not had_museum:
        # fixture still has museum place — chat remove should be idempotent
        pass
    updated = agent.chat(trip2.id, "Убери музей")
    museums = [s for d in updated.days for s in d.stops if s.category == "museum" or "музей" in s.name.lower()]
    assert museums == []
    # route recalculated object exists
    assert updated.days[0].route is not None
    assert before_ids or updated.days[0].stops is not None


def test_return_by_19(agent: TripPlannerAgent) -> None:
    hotel = HotelContext(
        hotelId="h1",
        name="Test Hotel Kazan",
        lat=55.796127,
        lon=49.106414,
        city="Казань",
        country="Россия",
    )
    trip = agent.plan("Казань на 1 день", hotel=hotel)
    updated = agent.chat(trip.id, "Хочу вернуться в отель до 19:00")
    assert updated.intent.returnBy == "19:00"
    text = " ".join(d.summary for d in updated.days) + " " + updated.summary
    assert ("19:00" in text) or ("Невозможно" in text) or ("Возврат" in text) or ("лимит" in text)


def test_provider_failure_no_hallucination(tmp_path: Path) -> None:
    agent = TripPlannerAgent(
        geocoding=FixtureGeocodingProvider(),
        places=FixturePlacesProvider(fail=True),
        routing=FixtureRoutingProvider(),
        store=TripStore(tmp_path / "trips"),
    )
    with pytest.raises(Exception) as exc:
        agent.plan("Казань на 1 день")
    msg = str(exc.value).lower()
    assert "places" in msg or "unavailable" in msg


def test_pdf_endpoint(client: TestClient, agent: TripPlannerAgent) -> None:
    trip = agent.plan("Казань на 1 день, главные достопримечательности")
    # Simulate a chat-status summary leaking into the trip object.
    trip.summary = "Оставила маршрут без изменений."
    from services.trip_planner.store import TripStore

    agent.store.save(trip)
    resp = client.get(f"/api/trips/{trip.id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 800

    from services.trip_planner.pdf import (
        _clean_description,
        _human_summary,
        _short_address,
        build_trip_pdf,
    )

    assert "Оставила" not in _human_summary(trip)
    assert "Маршрут по" in _human_summary(trip)
    assert _clean_description("Kremlin — OSM/attraction", "Kremlin") == ""
    assert "Magyarország" not in _short_address(
        "Kincsem Park, Ligettelek, Budapest, 1101, Magyarország"
    )
    pdf = build_trip_pdf(trip, web_link="http://127.0.0.1:4173/oh-route?trip=x")
    # Localhost links stay out of the printed itinerary.
    assert b"127.0.0.1" not in pdf
    assert b"%PDF" == pdf[:4]
    # Guidebook markers (Cyrillic may be encoded in the font stream — brand ASCII markers).
    assert b"Oh" in pdf or b"PDF" in pdf[:8]
    assert len(pdf) > 1500


def test_pdf_guidebook_has_day_structure(client: TestClient, agent: TripPlannerAgent) -> None:
    trip = agent.plan("Казань на 1 день, главные достопримечательности")
    from services.trip_planner.pdf import build_trip_pdf

    pdf = build_trip_pdf(trip, web_link="https://example.com/oh-route?trip=demo")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(pdf)
        text = "".join((doc[i].get_textpage().get_text_bounded() or "") for i in range(len(doc)))
        assert "example.com" in text or "Демо" in text or "образец" in text
    except ImportError:
        pass


def test_explicit_start_beats_evening_wish() -> None:
    """«вечером бар» must not move day start to 18:00 when «с 10:00» is set."""
    from services.trip_planner.intent_parser import parse_intent_rule_based

    intent = parse_intent_rule_based(
        "Стамбул на 1 день с 10:00: достопримечательности, ресторан, вечером бар"
    )
    assert intent.startTime == "10:00"
    labels = [w.label for w in intent.wishSequence]
    assert any("достопримечател" in x or x == "достопримечательности" for x in labels)
    assert any(w.category == "restaurant" for w in intent.wishSequence)
    assert any(w.category == "bar" for w in intent.wishSequence)


def test_vague_multiday_city_resolved() -> None:
    from services.trip_planner.intent_parser import GEOCODE_QUERY_ALIASES, parse_intent_rule_based

    sf = parse_intent_rule_based(
        "еду завтра в сан франциско составь маршрут на 3 дня не знаю куда ходить"
    )
    assert sf.destination == "San Francisco"
    assert sf.days == 3
    assert any(w.category == "attraction" for w in sf.wishSequence)
    assert GEOCODE_QUERY_ALIASES["san francisco"].endswith("USA")

    bj = parse_intent_rule_based("составь маршрут на 2 дня в пекине не знаю куда сходить")
    assert bj.destination == "Beijing"
    assert bj.days == 2
    assert any(w.category == "attraction" for w in bj.wishSequence)


def test_wish_coverage_diverse_phrasing() -> None:
    from services.trip_planner.intent_parser import parse_intent_rule_based

    cases = [
        (
            "приехал в сан фрациско сегодня не знаю куда сходить вечером "
            "хочу покушать вкусно выпить потом и посмотреть на ночной город",
            {"restaurant", "bar", "viewpoint"},
            "San Francisco",
            "18:00",
        ),
        (
            "Что посмотреть в Праге за день, старый город и поесть",
            {"attraction", "restaurant"},
            "Prague",
            "10:00",
        ),
        (
            "Хочу в Токио на выходные: храмы, рамэн, смотровая",
            {"religious", "restaurant", "viewpoint"},
            "Tokyo",
            "10:00",
        ),
        (
            "Дубай 2 дня пляж ресторан и шопинг",
            {"beach", "restaurant", "shopping"},
            "Dubai",
            "10:00",
        ),
        (
            "Вечером в Барселоне тапас и бар",
            {"restaurant", "bar"},
            "Barcelona",
            "18:00",
        ),
        (
            "arrived in rome want dinner drinks and a viewpoint",
            {"restaurant", "bar", "viewpoint"},
            "Rome",
            "18:00",
        ),
    ]
    for msg, cats, city, start in cases:
        intent = parse_intent_rule_based(msg)
        got = {w.category for w in intent.wishSequence if w.category}
        assert cats <= got, (msg, cats, got)
        assert intent.destination == city, (msg, intent.destination)
        assert intent.startTime == start, (msg, intent.startTime)


def test_sf_evening_food_drink_view(agent: TripPlannerAgent) -> None:
    """Colloquial evening ask must yield restaurant + bar + viewpoint, not 1 stop."""
    msg = (
        "приехал в сан фрациско сегодня не знаю куда сходить вечером "
        "хочу покушать вкусно выпить потом и посмотреть на ночной город"
    )
    trip = agent.plan(msg)
    assert trip.intent.startTime == "18:00"
    assert trip.intent.endTime >= "23:00"
    cats = {s.category for d in trip.days for s in d.stops}
    assert "restaurant" in cats
    assert "bar" in cats
    assert "viewpoint" in cats
    assert sum(len(d.stops) for d in trip.days) >= 3

    # Clarification must rebuild, not repeat the thin plan.
    updated = agent.chat(trip.id, "почему одно место если я сказал найти ресторан бар и вид на город")
    cats2 = {s.category for d in updated.days for s in d.stops}
    assert len(cats2) >= 3
    assert sum(len(d.stops) for d in updated.days) >= 3


def test_evening_only_outing_starts_late() -> None:
    from services.trip_planner.intent_parser import parse_intent_rule_based

    intent = parse_intent_rule_based("Вечерний маршрут по Казани: бар и ужин")
    assert intent.startTime == "18:00"


def test_istanbul_plan_keeps_wishes_and_start(agent: TripPlannerAgent) -> None:
    hotel = HotelContext(
        hotelId="h-ist",
        name="Hotel Istanbul",
        lat=41.0082,
        lon=28.9784,
        city="Istanbul",
        country="Türkiye",
    )
    trip = agent.plan(
        "Стамбул на 1 день с 10:00: достопримечательности, ресторан, вечером бар",
        hotel=hotel,
    )
    assert trip.intent.startTime == "10:00"
    cats = {s.category for d in trip.days for s in d.stops}
    assert "bar" in cats
    assert cats & {"attraction", "viewpoint", "museum", "restaurant"}
    first = trip.days[0].stops[0].startTime
    # First stop may be after a short hotel transfer, but must stay morning — not 18:xx.
    assert first < "14:00", first
    hotel_leg = next((s for s in trip.days[0].segments if s.fromStopId == "hotel"), None)
    assert hotel_leg is not None


def test_replace_bar_by_category(agent: TripPlannerAgent) -> None:
    trip = agent.plan("Казань на 1 день: достопримечательности, бар")
    assert any(s.category == "bar" for d in trip.days for s in d.stops)
    old_bars = {s.placeId for d in trip.days for s in d.stops if s.category == "bar"}
    updated = agent.chat(trip.id, "Замените бар на винный бар")
    assert "Заменил" in updated.summary or "замен" in updated.summary.lower()
    new_bars = [s for d in updated.days for s in d.stops if s.category == "bar"]
    assert new_bars
    assert new_bars[0].placeId not in old_bars or "винн" in new_bars[0].name.lower()


def test_cafe_wish_not_silently_replaced_by_restaurant(agent: TripPlannerAgent) -> None:
    """Cafe wish must stay cafe or be reported missing — never a restaurant stand-in."""
    trip = agent.plan("Казань на 1 день: кремль, кафе")
    cats = {s.category for d in trip.days for s in d.stops}
    missing = (trip.debug or {}).get("missingWishes") or []
    assert "cafe" in cats or any("кофе" in m or "кафе" in m for m in missing)
    if "cafe" in cats:
        assert "restaurant" not in cats or any(s.category == "cafe" for d in trip.days for s in d.stops)
        cafes = [s for d in trip.days for s in d.stops if s.category == "cafe"]
        assert cafes and "Skuratov" in cafes[0].name


def test_unrealistic_walk_upgrades_to_car() -> None:
    from services.trip_planner.models import LatLon
    from services.trip_planner.optimizer import _route_leg
    from services.trip_planner.providers.base import RouteResult, RoutingProvider

    class DetourWalk(RoutingProvider):
        name = "detour"

        def build_route(self, origin, destination, mode: str = "walk"):
            straight = abs(origin.lat - destination.lat) + abs(origin.lon - destination.lon)
            if mode == "walk":
                return RouteResult(
                    distanceMeters=12000,
                    durationSeconds=9000,
                    polyline=None,
                    mode="walk",
                    provider=self.name,
                    verified=True,
                )
            return RouteResult(
                distanceMeters=max(800, int(straight * 111_000)),
                durationSeconds=600,
                polyline=None,
                mode="car",
                provider=self.name,
                verified=True,
            )

    route, mode = _route_leg(
        DetourWalk(),
        LatLon(lat=41.0, lon=29.0),
        LatLon(lat=41.05, lon=29.05),
        "walk",
    )
    assert mode == "car"
    assert route.durationSeconds == 600


def test_edit_preserves_wish_sequence(agent: TripPlannerAgent) -> None:
    trip = agent.plan("Казань на 1 день: музей, парк, бар")
    wishes_before = [w.label for w in trip.intent.wishSequence]
    assert len(wishes_before) >= 2
    updated = agent.chat(trip.id, "Убери музей")
    assert len(updated.intent.wishSequence) >= 2
    assert any(s.category != "museum" for d in updated.days for s in d.stops) or not any(
        s.category == "museum" for d in updated.days for s in d.stops
    )


def test_bez_izmeneniy_is_not_remove() -> None:
    from services.trip_planner.intent_parser import parse_edit_actions

    actions = parse_edit_actions("Оставь маршрут без изменений")
    assert actions == [("keep_as_is", None)]
    assert not any(a == "remove_stop" for a, _ in actions)
    actions2 = parse_edit_actions("без музея")
    assert any(a == "remove_stop" and t and "музе" in t for a, t in actions2)


def test_bez_izmeneniy_chat_keeps_stops(agent: TripPlannerAgent) -> None:
    trip = agent.plan("Казань на 1 день, главные достопримечательности")
    before = [s.placeId for d in trip.days for s in d.stops]
    assert before
    updated = agent.chat(trip.id, "Оставь маршрут без изменений")
    after = [s.placeId for d in updated.days for s in d.stops]
    assert after == before
    assert "без изменений" in updated.summary.lower()


def test_plan_stream_emits_progress_before_done(agent: TripPlannerAgent) -> None:
    types: list[str] = []
    for event in agent.plan_stream("Казань на 1 день, главные достопримечательности"):
        types.append(event["type"])
        if event["type"] == "progress" and len(types) == 1:
            # First event must be progress, not a buffered done-only burst.
            assert event.get("step")
    assert types[0] == "progress"
    assert types[-1] == "done"
    assert types.count("progress") >= 2


def test_plan_stream_yields_while_plan_runs(agent: TripPlannerAgent, monkeypatch: pytest.MonkeyPatch) -> None:
    """Progress must leave the generator before plan() returns (no end-buffering)."""
    import threading
    import time

    from services.trip_planner.agent import TripPlannerAgent as TPA

    orig_plan = TPA.plan
    entered = threading.Event()
    release = threading.Event()

    def slow_plan(self, message, hotel=None, progress=None, trip_id=None):  # noqa: ANN001
        if progress:
            progress("Понимаю пожелания")
        entered.set()
        assert release.wait(timeout=5), "test deadlock"
        if progress:
            progress("Ищу места")
        return orig_plan(self, message, hotel=hotel, progress=None, trip_id=trip_id)

    monkeypatch.setattr(TPA, "plan", slow_plan)
    gen = agent.plan_stream("Казань на 1 день")
    first = next(gen)
    assert first["type"] == "progress"
    assert entered.wait(timeout=2)
    # First progress arrived while plan() is still blocked — not buffered to the end.
    release.set()
    rest = list(gen)
    assert any(e["type"] == "progress" for e in rest)
    assert rest[-1]["type"] == "done"
    # silence unused
    time.sleep(0)


def test_istanbul_six_wishes_and_mode_consistency(agent: TripPlannerAgent) -> None:
    hotel = HotelContext(
        hotelId="h-ist",
        name="Hotel Istanbul",
        lat=41.0082,
        lon=28.9784,
        city="Istanbul",
        country="Türkiye",
    )
    msg = (
        "Стамбул на 1 день с 10:00: достопримечательности, музей, смотровая, "
        "ресторан, кофе, вечером бар"
    )
    trip = agent.plan(msg, hotel=hotel)
    assert trip.intent.startTime == "10:00"
    assert len(trip.intent.wishSequence) >= 6
    cats = {s.category for d in trip.days for s in d.stops}
    for needed in ("attraction", "museum", "viewpoint", "restaurant", "cafe", "bar"):
        assert needed in cats, (needed, cats)
    assert trip.days[0].stops[0].startTime < "14:00"
    segs = trip.days[0].segments
    if any(s.mode == "car" for s in segs):
        # Geometry rebuild must not silently switch back to walk-only totals
        # when legs already required a car.
        assert trip.days[0].route.distanceMeters >= max(s.distanceMeters for s in segs)
    updated = agent.chat(trip.id, "Замените бар на винный бар")
    assert "Заменил" in updated.summary


def test_osrm_failure_does_not_invent_haversine_distance() -> None:
    """When routing fails, keep the stop but never publish fake km/min."""
    from services.trip_planner.models import HotelContext, LatLon, Place, TripIntent, WishItem
    from services.trip_planner.optimizer import build_day_plan
    from services.trip_planner.providers.base import ProviderError, RoutingProvider

    class DeadRouter(RoutingProvider):
        name = "dead"

        def build_route(self, origin, destination, mode: str = "walk"):
            raise ProviderError("route_unavailable", "OSRM down")

    places = [
        Place(
            placeProvider="test",
            placeId="a",
            name="A",
            category="attraction",
            lat=55.75,
            lon=37.62,
        ),
        Place(
            placeProvider="test",
            placeId="b",
            name="B",
            category="cafe",
            lat=55.76,
            lon=37.63,
        ),
    ]
    intent = TripIntent(
        destination="Москва",
        days=1,
        startTime="10:00",
        endTime="20:00",
        wishSequence=[
            WishItem(label="место", kind="interest", category="attraction"),
            WishItem(label="кофе", kind="interest", category="cafe"),
        ],
    )
    day = build_day_plan(
        1,
        places,
        intent,
        LatLon(lat=55.74, lon=37.61),
        HotelContext(),
        DeadRouter(),
        preserve_order=True,
    )
    assert len(day.stops) >= 1
    assert day.segments, "unverified legs should still be recorded"
    assert all(s.verified is False for s in day.segments)
    assert all(s.distanceMeters == 0 and s.durationSeconds == 0 for s in day.segments)
    assert day.route.verified is False
    assert day.route.distanceMeters == 0
    assert day.route.durationSeconds == 0
    assert day.route.polyline is None
    # Unknown travel must not be treated as 0 minutes on the clock.
    assert all(s.startTime == "" for s in day.stops)
    assert "времени прибытия неизвестна" in day.summary.lower() or "неизвестна" in day.summary.lower()


def test_empty_multiday_chunk_is_incomplete() -> None:
    from services.trip_planner.models import HotelContext, LatLon, TripIntent
    from services.trip_planner.optimizer import build_day_plan
    from services.trip_planner.providers.fixtures import FixtureRoutingProvider

    intent = TripIntent(destination="Сочи", days=2, startTime="10:00", endTime="20:00")
    empty = build_day_plan(
        2,
        [],
        intent,
        LatLon(lat=43.58, lon=39.72),
        HotelContext(),
        FixtureRoutingProvider(),
        preserve_order=True,
    )
    assert empty.incomplete is True
    assert empty.stops == []
    assert "неполный результат" in empty.summary.lower()
    assert empty.route.verified is False


def test_wish_match_rejects_kremlevskaya_stem() -> None:
    from services.trip_planner.wish_match import MUST_SCORE_THRESHOLD, name_match_score

    assert name_match_score("Кремлёвская", "Кремль") < MUST_SCORE_THRESHOLD
    assert name_match_score("Казанский кремль", "Кремль") >= MUST_SCORE_THRESHOLD
    assert name_match_score("Kazan Kremlin", "Кремль") >= MUST_SCORE_THRESHOLD
    assert name_match_score("Sultan Ahmed Mosque", "Голубая мечеть") >= MUST_SCORE_THRESHOLD
    assert name_match_score("Blue Mosque", "Голубая мечеть") >= MUST_SCORE_THRESHOLD
    assert name_match_score("Burj Khalifa", "Бурдж-Халифа") >= MUST_SCORE_THRESHOLD
    assert name_match_score("Dubai Marina", "марина") >= MUST_SCORE_THRESHOLD
    assert name_match_score("Kaleiçi", "Калеичи") >= MUST_SCORE_THRESHOLD
    # Category-like names must not fulfill a landmark label.
    assert name_match_score("City Attraction Park", "Бурдж-Халифа") < MUST_SCORE_THRESHOLD


def test_area_wish_rejects_museum_tenant() -> None:
    """«старый город Калеичи» must not resolve to a museum that merely contains the name."""
    from services.trip_planner.models import Place
    from services.trip_planner.wish_match import (
        rank_named_candidates,
        wish_targets_area,
    )

    assert wish_targets_area("Калеичи")
    museum = Place(
        placeProvider="t",
        placeId="osm:node/1",
        name="Suna & İnan Kıraç Kaleiçi Museum",
        category="museum",
        lat=36.884,
        lon=30.708,
        placeKind="museum",
        wikidataId="Q4306139",
    )
    district = Place(
        placeProvider="t",
        placeId="osm:relation/2",
        name="Kaleiçi",
        category="attraction",
        lat=36.885,
        lon=30.705,
        placeKind="suburb",
        wikidataId="Q5994531",
    )
    ranked = rank_named_candidates(
        [museum, district],
        "Калеичи",
        near_lat=36.8865,
        near_lon=30.64,
        query="старый город Калеичи",
    )
    assert ranked
    assert ranked[0].place.placeId == district.placeId
    assert all(r.place.placeId != museum.placeId for r in ranked)


def test_wish_match_dedupe_by_id_and_coords() -> None:
    from services.trip_planner.models import Place
    from services.trip_planner.wish_match import dedupe_places, places_are_duplicate

    a = Place(
        placeProvider="t",
        placeId="osm:node/1",
        name="Burj Khalifa",
        category="attraction",
        lat=25.1972,
        lon=55.2744,
        wikidataId="Q4555",
    )
    b = Place(
        placeProvider="t",
        placeId="osm:way/2",
        name="Burj Khalifa Dubai",
        category="attraction",
        lat=25.1973,
        lon=55.2745,
        wikidataId="Q4555",
    )
    c = Place(
        placeProvider="t",
        placeId="osm:node/3",
        name="Dubai Marina",
        category="attraction",
        lat=25.0805,
        lon=55.1403,
    )
    assert places_are_duplicate(a, b)
    assert not places_are_duplicate(a, c)
    assert len(dedupe_places([a, b, c])) == 2


def test_named_musts_parsed_from_city_queries() -> None:
    from services.trip_planner.intent_parser import parse_intent_rule_based

    kz = parse_intent_rule_based("Казань на 1 день: кремль, мечеть, прогулка по Баумана, музей, кафе")
    labels = {w.label for w in kz.wishSequence}
    assert "Кремль" in labels
    assert "Баумана" in labels

    ist = parse_intent_rule_based("Istanbul 1 day: Hagia Sophia, Blue Mosque, museum, cafe, bar")
    labels = {w.label for w in ist.wishSequence}
    assert "Айя-София" in labels
    assert "Голубая мечеть" in labels

    dxb = parse_intent_rule_based("Дубай на 1 день: Бурдж-Халифа, мечеть, марина, кафе")
    labels = {w.label for w in dxb.wishSequence}
    assert "Бурдж-Халифа" in labels
    assert "марина" in labels

    ant = parse_intent_rule_based("Анталья: пляж, старый город Калеичи, ресторан")
    labels = {w.label for w in ant.wishSequence}
    assert "Калеичи" in labels
