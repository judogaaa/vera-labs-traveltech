from __future__ import annotations

import json
from typing import Any, Callable

from services.ai.gigachat_types import FunctionDef

from .models import HotelContext, LatLon, Place, Trip
from .optimizer import build_day_plan, recalculate_day_routes
from .providers.base import GeocodingProvider, PlacesProvider, ProviderError, RoutingProvider


TOOL_DEFS: list[FunctionDef] = [
    FunctionDef(
        name="geocode_destination",
        description="Геокодинг города/адреса в координаты. Единственный источник координат destination.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Название города или места"}},
            "required": ["query"],
        },
    ),
    FunctionDef(
        name="search_places",
        description="Поиск реальных POI рядом с точкой. Не выдумывай места вне результатов.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "radiusMeters": {"type": "integer"},
                "category": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query", "lat", "lon"],
        },
    ),
    FunctionDef(
        name="get_place_details",
        description="Детали места по placeId из провайдера.",
        parameters={
            "type": "object",
            "properties": {"placeId": {"type": "string"}},
            "required": ["placeId"],
        },
    ),
    FunctionDef(
        name="find_places_near_hotel",
        description="Поиск POI рядом с отелем (home base).",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {"type": "string"},
                "radiusMeters": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    ),
    FunctionDef(
        name="calculate_route",
        description="Маршрут между двумя точками. Единственный источник distance/time.",
        parameters={
            "type": "object",
            "properties": {
                "originLat": {"type": "number"},
                "originLon": {"type": "number"},
                "destLat": {"type": "number"},
                "destLon": {"type": "number"},
                "mode": {"type": "string", "enum": ["walk", "car", "transit"]},
            },
            "required": ["originLat", "originLon", "destLat", "destLon"],
        },
    ),
    FunctionDef(
        name="calculate_multi_stop_route",
        description="Мультиточечный маршрут по списку координат.",
        parameters={
            "type": "object",
            "properties": {
                "stops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
                        "required": ["lat", "lon"],
                    },
                },
                "mode": {"type": "string", "enum": ["walk", "car", "transit"]},
            },
            "required": ["stops"],
        },
    ),
    FunctionDef(
        name="add_stop",
        description="Добавить verified placeId в день itinerary.",
        parameters={
            "type": "object",
            "properties": {
                "dayNumber": {"type": "integer"},
                "placeId": {"type": "string"},
            },
            "required": ["dayNumber", "placeId"],
        },
    ),
    FunctionDef(
        name="remove_stop",
        description="Удалить остановку по имени/категории/id из itinerary.",
        parameters={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Имя, категория или id остановки"},
                "dayNumber": {"type": "integer"},
            },
            "required": ["target"],
        },
    ),
    FunctionDef(
        name="replace_stop",
        description="Заменить остановку на другой verified placeId.",
        parameters={
            "type": "object",
            "properties": {
                "dayNumber": {"type": "integer"},
                "oldPlaceId": {"type": "string"},
                "newPlaceId": {"type": "string"},
            },
            "required": ["dayNumber", "oldPlaceId", "newPlaceId"],
        },
    ),
    FunctionDef(
        name="reorder_stops",
        description="Изменить порядок остановок дня по списку stop ids.",
        parameters={
            "type": "object",
            "properties": {
                "dayNumber": {"type": "integer"},
                "stopIds": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["dayNumber", "stopIds"],
        },
    ),
    FunctionDef(
        name="rebuild_day",
        description="Пересобрать день из списка verified placeIds с маршрутизацией.",
        parameters={
            "type": "object",
            "properties": {
                "dayNumber": {"type": "integer"},
                "placeIds": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["dayNumber", "placeIds"],
        },
    ),
]


class TripToolExecutor:
    def __init__(
        self,
        geocoding: GeocodingProvider,
        places: PlacesProvider,
        routing: RoutingProvider,
        *,
        hotel: HotelContext | None = None,
        trip: Trip | None = None,
    ) -> None:
        self.geocoding = geocoding
        self.places = places
        self.routing = routing
        self.hotel = hotel
        self.trip = trip
        self.calls: list[str] = []
        self.route_calls = 0
        self.place_calls = 0
        # Side-effect store so the agent can recover POIs after the tool loop
        # (previously places were discarded because the orchestrator returned []).
        self.collected_places: dict[str, Any] = {}
        self.last_geocode: dict[str, Any] | None = None

    def __call__(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(name)
        handler: Callable[[dict[str, Any]], dict[str, Any]] | None = getattr(self, f"tool_{name}", None)
        if not handler:
            return {"error": "unknown_tool", "message": f"Unknown tool: {name}"}
        try:
            return handler(args)
        except ProviderError as exc:
            return {"error": exc.code, "message": exc.message}
        except Exception as exc:  # noqa: BLE001
            return {"error": "tool_failed", "message": str(exc)[:300]}

    def tool_geocode_destination(self, args: dict[str, Any]) -> dict[str, Any]:
        ll = self.geocoding.geocode(str(args.get("query") or ""))
        if not ll:
            return {"error": "city_not_found", "message": "Город не найден"}
        rev = self.geocoding.reverse_geocode(ll.lat, ll.lon)
        out = {
            "lat": ll.lat,
            "lon": ll.lon,
            "name": rev.get("city") or args.get("query"),
            "country": rev.get("country") or "",
            "address": rev.get("address") or "",
        }
        self.last_geocode = out
        return out

    def _remember_places(self, results: list[Any]) -> None:
        for p in results:
            pid = (
                getattr(p, "placeId", None)
                or getattr(p, "id", None)
                or (p.get("placeId") if isinstance(p, dict) else None)
                or (p.get("id") if isinstance(p, dict) else None)
            )
            if pid:
                self.collected_places[str(pid)] = p

    def tool_search_places(self, args: dict[str, Any]) -> dict[str, Any]:
        self.place_calls += 1
        results = self.places.search_places(
            query=str(args.get("query") or ""),
            near=LatLon(lat=float(args["lat"]), lon=float(args["lon"])),
            radius=int(args.get("radiusMeters") or 5000),
            category=args.get("category"),
            limit=int(args.get("limit") or 12),
        )
        self._remember_places(results)
        return {"places": [p.model_dump() for p in results], "provider": self.places.name}

    def tool_get_place_details(self, args: dict[str, Any]) -> dict[str, Any]:
        self.place_calls += 1
        place = self.places.get_place_details(str(args.get("placeId") or ""))
        if not place:
            return {"error": "not_found", "message": "Место не найдено"}
        return place.model_dump()

    def tool_find_places_near_hotel(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.hotel or self.hotel.lat is None or self.hotel.lon is None:
            return {"error": "no_hotel", "message": "Отель не задан"}
        self.place_calls += 1
        results = self.places.search_places(
            query=str(args.get("query") or "attraction"),
            near=LatLon(lat=self.hotel.lat, lon=self.hotel.lon),
            radius=int(args.get("radiusMeters") or 8000),
            category=args.get("category"),
            limit=int(args.get("limit") or 12),
        )
        self._remember_places(results)
        return {"places": [p.model_dump() for p in results], "provider": self.places.name}

    def tool_calculate_route(self, args: dict[str, Any]) -> dict[str, Any]:
        self.route_calls += 1
        mode = str(args.get("mode") or "walk")
        route = self.routing.build_route(
            LatLon(lat=float(args["originLat"]), lon=float(args["originLon"])),
            LatLon(lat=float(args["destLat"]), lon=float(args["destLon"])),
            mode=mode,
        )
        return {
            "distanceMeters": route.distanceMeters,
            "durationSeconds": route.durationSeconds,
            "polyline": route.polyline,
            "mode": route.mode,
            "provider": route.provider,
            "verified": route.verified,
        }

    def tool_calculate_multi_stop_route(self, args: dict[str, Any]) -> dict[str, Any]:
        self.route_calls += 1
        stops_raw = args.get("stops") or []
        stops = [LatLon(lat=float(s["lat"]), lon=float(s["lon"])) for s in stops_raw]
        route = self.routing.build_multi_stop_route(stops, mode=str(args.get("mode") or "walk"))
        return {
            "distanceMeters": route.distanceMeters,
            "durationSeconds": route.durationSeconds,
            "polyline": route.polyline,
            "mode": route.mode,
            "provider": route.provider,
            "verified": route.verified,
        }

    def tool_add_stop(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.trip:
            return {"error": "no_trip", "message": "Нет текущего itinerary"}
        place = self.places.get_place_details(str(args["placeId"]))
        if not place:
            # try search cache via details failure
            return {"error": "not_found", "message": "placeId не найден у провайдера"}
        day_n = int(args.get("dayNumber") or 1)
        day = next((d for d in self.trip.days if d.dayNumber == day_n), None)
        if not day:
            return {"error": "no_day", "message": f"День {day_n} не найден"}
        places = [_stop_as_place(s) for s in day.stops] + [place]
        home = _home(self.trip)
        rebuilt = build_day_plan(day_n, places, self.trip.intent, home, self.trip.hotel, self.routing, preserve_order=True)
        self.trip.days = [rebuilt if d.dayNumber == day_n else d for d in self.trip.days]
        return {"ok": True, "day": rebuilt.model_dump()}

    def tool_remove_stop(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.trip:
            return {"error": "no_trip", "message": "Нет текущего itinerary"}
        target = str(args.get("target") or "").lower()
        day_n = args.get("dayNumber")
        removed = 0
        for day in self.trip.days:
            if day_n and day.dayNumber != int(day_n):
                continue
            before = len(day.stops)
            day.stops = [
                s
                for s in day.stops
                if not (
                    target in s.name.lower()
                    or target in s.category.lower()
                    or target == s.id.lower()
                    or target == s.placeId.lower()
                    or ("музей" in target and s.category == "museum")
                )
            ]
            removed += before - len(day.stops)
            home = _home(self.trip)
            updated = recalculate_day_routes(day, home, self.routing, self.trip.intent.transportPreference)
            day.segments = updated.segments
            day.route = updated.route
        return {"ok": True, "removed": removed}

    def tool_replace_stop(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.trip:
            return {"error": "no_trip", "message": "Нет текущего itinerary"}
        new_place = self.places.get_place_details(str(args["newPlaceId"]))
        if not new_place:
            return {"error": "not_found", "message": "newPlaceId не найден"}
        day_n = int(args["dayNumber"])
        day = next((d for d in self.trip.days if d.dayNumber == day_n), None)
        if not day:
            return {"error": "no_day", "message": "День не найден"}
        places: list[Place] = []
        for s in day.stops:
            if s.placeId == args["oldPlaceId"]:
                places.append(new_place)
            else:
                places.append(_stop_as_place(s))
        home = _home(self.trip)
        rebuilt = build_day_plan(day_n, places, self.trip.intent, home, self.trip.hotel, self.routing, preserve_order=True)
        self.trip.days = [rebuilt if d.dayNumber == day_n else d for d in self.trip.days]
        return {"ok": True, "day": rebuilt.model_dump()}

    def tool_reorder_stops(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.trip:
            return {"error": "no_trip", "message": "Нет текущего itinerary"}
        day_n = int(args["dayNumber"])
        day = next((d for d in self.trip.days if d.dayNumber == day_n), None)
        if not day:
            return {"error": "no_day", "message": "День не найден"}
        by_id = {s.id: s for s in day.stops}
        ordered = [by_id[i] for i in args.get("stopIds") or [] if i in by_id]
        for s in day.stops:
            if s.id not in {x.id for x in ordered}:
                ordered.append(s)
        day.stops = ordered
        home = _home(self.trip)
        updated = recalculate_day_routes(day, home, self.routing, self.trip.intent.transportPreference)
        day.segments = updated.segments
        day.route = updated.route
        return {"ok": True, "stopIds": [s.id for s in day.stops]}

    def tool_rebuild_day(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.trip:
            return {"error": "no_trip", "message": "Нет текущего itinerary"}
        places: list[Place] = []
        for pid in args.get("placeIds") or []:
            p = self.places.get_place_details(str(pid))
            if p:
                places.append(p)
        if len(places) < 1:
            return {"error": "not_enough_places", "message": "Нет verified мест для дня"}
        day_n = int(args["dayNumber"])
        home = _home(self.trip)
        rebuilt = build_day_plan(day_n, places, self.trip.intent, home, self.trip.hotel, self.routing, preserve_order=True)
        self.trip.days = [rebuilt if d.dayNumber == day_n else d for d in self.trip.days]
        return {"ok": True, "day": rebuilt.model_dump()}


def _home(trip: Trip) -> LatLon:
    if trip.hotel.lat is not None and trip.hotel.lon is not None:
        return LatLon(lat=trip.hotel.lat, lon=trip.hotel.lon)
    return LatLon(lat=trip.destination.lat, lon=trip.destination.lon)


def _stop_as_place(s: Any) -> Place:
    return Place(
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


def load_system_prompt() -> str:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "prompts" / "trip_planner_system_v1.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Ты оркестратор trip planner. Не выдумывай POI. Используй только tools."
