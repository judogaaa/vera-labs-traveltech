from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta

from .models import (
    DayPlan,
    DayRoute,
    HotelContext,
    LatLon,
    Place,
    Stop,
    TravelSegment,
    TripIntent,
)
from .providers.base import ProviderError, RouteResult, RoutingProvider


def _parse_hhmm(value: str) -> datetime:
    h, m = value.split(":")
    base = datetime(2000, 1, 1, int(h), int(m))
    return base


def _fmt_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _haversine_m(a: LatLon, b: LatLon) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi = math.radians(b.lat - a.lat)
    dlmb = math.radians(b.lon - a.lon)
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def cluster_and_order(
    places: list[Place],
    home: LatLon,
    days: int,
    pace: str,
) -> list[list[Place]]:
    """Greedy geographic clustering from home; no invented places."""
    if not places:
        return [[] for _ in range(days)]

    per_day = {"relaxed": 3, "normal": 4, "intensive": 5}.get(pace, 4)
    remaining = list(places)
    # nearest-neighbor tour from home, then chunk
    ordered: list[Place] = []
    current = home
    while remaining:
        remaining.sort(key=lambda p: _haversine_m(current, LatLon(lat=p.lat, lon=p.lon)))
        nxt = remaining.pop(0)
        ordered.append(nxt)
        current = LatLon(lat=nxt.lat, lon=nxt.lon)

    chunks: list[list[Place]] = []
    for i in range(days):
        start = i * per_day
        chunk = ordered[start : start + per_day]
        chunks.append(chunk)
    # leftover into last day if small
    leftover = ordered[days * per_day :]
    if leftover and chunks:
        chunks[-1].extend(leftover[:2])
    while len(chunks) < days:
        chunks.append([])
    return chunks[:days]


def place_to_stop(place: Place, start: datetime, duration: int) -> Stop:
    return Stop(
        id=f"stop_{uuid.uuid4().hex[:10]}",
        placeProvider=place.placeProvider,
        placeId=place.placeId,
        name=place.name,
        category=place.category,
        lat=place.lat,
        lon=place.lon,
        address=place.address,
        startTime=_fmt_hhmm(start),
        durationMinutes=duration,
        description=place.description,
        photoUrl=place.photoUrl,
        rating=place.rating,
        ratingCount=place.ratingCount,
        website=place.website,
        wikidataId=getattr(place, "wikidataId", None),
    )


# Comfortable walking budget; longer legs become car (geometry + car timing).
_WALK_MAX_METERS = 2500
_WALK_MAX_SECONDS = 35 * 60
_WALK_DETOUR_RATIO = 2.5
_WALK_DETOUR_MIN_STRAIGHT_M = 1000
# If a "walk" result implies > this speed, treat it as a lying car profile.
_WALK_IMPLIED_MAX_KMH = 7.0


def _implied_kmh(distance_m: int, duration_s: int) -> float:
    if duration_s <= 0:
        return 999.0
    return (distance_m / duration_s) * 3.6


def _route_leg(
    routing: RoutingProvider,
    origin: LatLon,
    dest: LatLon,
    preferred: str,
) -> tuple[object, str]:
    """Return (route, mode). Never label car-speed timings as walk."""
    mode = preferred if preferred in {"walk", "car", "transit"} else "walk"
    if mode == "transit":
        mode = "walk"
    route = routing.build_route(origin, dest, mode=mode)
    if mode != "walk":
        return route, mode

    straight = _haversine_m(origin, dest)
    detour = route.distanceMeters / max(straight, 1.0)
    speed = _implied_kmh(route.distanceMeters, route.durationSeconds)
    unrealistic = (
        route.durationSeconds > _WALK_MAX_SECONDS
        or route.distanceMeters > _WALK_MAX_METERS
        or speed > _WALK_IMPLIED_MAX_KMH
        or (straight >= _WALK_DETOUR_MIN_STRAIGHT_M and detour > _WALK_DETOUR_RATIO)
    )
    if not unrealistic:
        return route, "walk"
    try:
        car = routing.build_route(origin, dest, mode="car")
        return car, "car"
    except ProviderError:
        # Prefer car label only when we have car timing. If car fails, keep the
        # walk result — OsrmRoutingProvider already rewrites impossible speeds.
        return route, "walk"


def build_day_plan(
    day_number: int,
    places: list[Place],
    intent: TripIntent,
    home: LatLon | None,
    hotel: HotelContext | None,
    routing: RoutingProvider,
    preserve_order: bool = False,
) -> DayPlan:
    # Multi-day plans may pad with empty chunks when few places were found.
    # Soft-empty day keeps a usable trip instead of failing the whole request —
    # but must be labelled as an incomplete result, not a full day plan.
    if not places:
        return DayPlan(
            dayNumber=day_number,
            summary=(
                f"День {day_number}: неполный результат — мало подтверждённых мест "
                "на этот день. Уточните пожелания или район."
            ),
            incomplete=True,
            route=DayRoute(verified=False),
        )

    start = _parse_hhmm(intent.startTime)
    end = _parse_hhmm(intent.returnBy or intent.endTime)
    if end <= start:
        end = start + timedelta(hours=8)

    lunch_window = (_parse_hhmm("13:00"), _parse_hhmm("15:00"))

    preferred = intent.transportPreference if intent.transportPreference != "mixed" else "walk"
    if preferred == "transit":
        preferred = "walk"

    cursor = start
    stops: list[Stop] = []
    segments: list[TravelSegment] = []
    prev_ll = home
    prev_id: str | None = None
    total_dist = 0
    total_dur = 0
    polyline_parts: list[str] = []
    # Once a leg cannot be routed, later clock times are unknown — never treat
    # missing travel as 0 minutes on the schedule.
    schedule_known = True

    # Dwell time depends on what the place IS, not only on pace.
    base_dur = {
        "restaurant": 75,
        "beach": 120,
        "bar": 40,
        "cafe": 40,
        "viewpoint": 45,
        "museum": 60,
        "park": 60,
        "attraction": 60,
    }
    pace_mult = {"relaxed": 1.25, "normal": 1.0, "intensive": 0.75}

    # Prefer restaurant near lunch (unless the user fixed the order of wishes)
    ordered = list(places)
    if not preserve_order:
        for i, place in enumerate(list(ordered)):
            if place.category == "restaurant" and lunch_window[0] <= cursor <= lunch_window[1]:
                ordered.insert(0, ordered.pop(i))
                break

    for place in ordered:
        if schedule_known and cursor >= end:
            break
        ll = LatLon(lat=place.lat, lon=place.lon)
        pending_seg: TravelSegment | None = None
        if prev_ll is not None:
            try:
                route, leg_mode = _route_leg(routing, prev_ll, ll, preferred)
            except ProviderError:
                # Keep the place, but never invent haversine km/min or pretend
                # travel took 0 minutes on the clock.
                from_id = prev_id if prev_id else "hotel"
                pending_seg = TravelSegment(
                    fromStopId=from_id,
                    toStopId="pending",
                    mode=preferred if preferred in {"walk", "car", "transit"} else "walk",  # type: ignore[arg-type]
                    distanceMeters=0,
                    durationSeconds=0,
                    verified=False,
                    polyline=None,
                )
                schedule_known = False
            else:
                travel = timedelta(seconds=route.durationSeconds)
                if schedule_known and cursor + travel >= end:
                    # Skip this place, try next one
                    continue
                if schedule_known:
                    cursor = cursor + travel
                from_id = prev_id if prev_id else "hotel"
                pending_seg = TravelSegment(
                    fromStopId=from_id,
                    toStopId="pending",
                    mode=leg_mode,  # type: ignore[arg-type]
                    distanceMeters=route.distanceMeters,
                    durationSeconds=route.durationSeconds,
                    verified=True,
                    polyline=route.polyline,
                )
                total_dist += route.distanceMeters
                total_dur += route.durationSeconds
                if route.polyline:
                    polyline_parts.append(route.polyline)

        stop_dur = int(
            base_dur.get(place.category, 60) * pace_mult.get(intent.pace, 1.0)
        )
        if schedule_known:
            if cursor + timedelta(minutes=stop_dur) > end:
                remaining = int((end - cursor).total_seconds() / 60)
                if remaining < 30:
                    continue
                stop_dur = remaining
            stop = place_to_stop(place, cursor, stop_dur)
            cursor = cursor + timedelta(minutes=stop_dur)
        else:
            # Arrival time unknown after unverified travel — leave startTime blank.
            stop = place_to_stop(place, start, stop_dur).model_copy(update={"startTime": ""})

        if pending_seg is not None:
            segments.append(pending_seg.model_copy(update={"toStopId": stop.id}))
        stops.append(stop)
        prev_id = stop.id
        prev_ll = ll

    # If no stops could be placed, fail with route_impossible
    if not stops:
        raise ProviderError(
            "route_impossible",
            "Не удалось построить маршрут в заданном окне времени — ни одно место не доступно."
        )

    names = ", ".join(s.name for s in stops[:3])
    summary = f"День {day_number}: {names}" if stops else f"День {day_number}: нет подтверждённых мест"
    if any(not s.startTime for s in stops):
        summary = (
            f"{summary} Часть времени прибытия неизвестна — "
            "переезд без подтверждённого маршрута."
        )

    # Day overview polyline only when *all* verified legs share one mode.
    # Mixed walk+car days keep per-leg polylines so car geometry is not shown as walk.
    route_polyline = polyline_parts[0] if len(polyline_parts) == 1 else None
    legs_verified = all(s.verified for s in segments) if segments else True
    modes = {s.mode for s in segments if s.verified}
    same_mode = len(modes) == 1
    summary_mode = next(iter(modes)) if same_mode else preferred
    if legs_verified and same_mode and len(stops) >= 2:
        points = ([home] if home is not None else []) + [LatLon(lat=s.lat, lon=s.lon) for s in stops]
        try:
            route_all = routing.build_multi_stop_route(points, mode=summary_mode)
            if route_all.polyline:
                route_polyline = route_all.polyline
            if route_all.distanceMeters > 0:
                total_dist = route_all.distanceMeters
                total_dur = route_all.durationSeconds
        except ProviderError:
            # Legs remain verified; map draws each segment.polyline instead.
            route_polyline = None
    elif not same_mode:
        # Mixed modes: never collapse into one car overview line.
        route_polyline = None
        total_dist = sum(s.distanceMeters for s in segments if s.verified)
        total_dur = sum(s.durationSeconds for s in segments if s.verified)

    return DayPlan(
        dayNumber=day_number,
        summary=summary,
        stops=stops,
        segments=segments,
        incomplete=False,
        route=DayRoute(
            distanceMeters=sum(s.distanceMeters for s in segments if s.verified)
            if not legs_verified
            else total_dist,
            durationSeconds=sum(s.durationSeconds for s in segments if s.verified)
            if not legs_verified
            else total_dur,
            polyline=route_polyline if legs_verified else None,
            verified=legs_verified,
        ),
    )


def recalculate_day_routes(
    day: DayPlan,
    home: LatLon | None,
    routing: RoutingProvider,
    mode: str = "walk",
) -> DayPlan:
    preferred = mode
    if preferred in {"transit", "mixed"}:
        preferred = "walk"
    segments: list[TravelSegment] = []
    total_dist = 0
    total_dur = 0
    prev_ll = home
    prev_id: str | None = None
    for stop in day.stops:
        ll = LatLon(lat=stop.lat, lon=stop.lon)
        if prev_ll is not None:
            from_id = prev_id if prev_id else "hotel"
            try:
                route, leg_mode = _route_leg(routing, prev_ll, ll, preferred)
                segments.append(
                    TravelSegment(
                        fromStopId=from_id,
                        toStopId=stop.id,
                        mode=leg_mode,  # type: ignore[arg-type]
                        distanceMeters=route.distanceMeters,
                        durationSeconds=route.durationSeconds,
                        verified=True,
                        polyline=route.polyline,
                    )
                )
                total_dist += route.distanceMeters
                total_dur += route.durationSeconds
            except ProviderError:
                segments.append(
                    TravelSegment(
                        fromStopId=from_id,
                        toStopId=stop.id,
                        mode=preferred if preferred in {"walk", "car", "transit"} else "walk",  # type: ignore[arg-type]
                        distanceMeters=0,
                        durationSeconds=0,
                        verified=False,
                        polyline=None,
                    )
                )
        prev_ll = ll
        prev_id = stop.id
    route_polyline = None
    legs_verified = all(s.verified for s in segments) if segments else True
    modes = {s.mode for s in segments if s.verified}
    same_mode = len(modes) == 1
    summary_mode = next(iter(modes)) if same_mode else preferred
    if legs_verified and same_mode and len(day.stops) >= 2:
        points = ([home] if home is not None else []) + [LatLon(lat=s.lat, lon=s.lon) for s in day.stops]
        try:
            route_all = routing.build_multi_stop_route(points, mode=summary_mode)
            if route_all.polyline:
                route_polyline = route_all.polyline
            if route_all.distanceMeters > 0:
                total_dist = route_all.distanceMeters
                total_dur = route_all.durationSeconds
        except ProviderError:
            route_polyline = None
    elif not same_mode:
        route_polyline = None
        total_dist = sum(s.distanceMeters for s in segments if s.verified)
        total_dur = sum(s.durationSeconds for s in segments if s.verified)
    return day.model_copy(
        update={
            "segments": segments,
            "route": DayRoute(
                distanceMeters=total_dist if legs_verified else sum(
                    s.distanceMeters for s in segments if s.verified
                ),
                durationSeconds=total_dur if legs_verified else sum(
                    s.durationSeconds for s in segments if s.verified
                ),
                polyline=route_polyline if legs_verified else None,
                verified=legs_verified,
            ),
        }
    )
