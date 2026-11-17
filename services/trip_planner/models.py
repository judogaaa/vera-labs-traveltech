from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import config


TransportMode = Literal["walk", "car", "transit", "mixed"]

# Trip ids are always server-generated: "trip_" + 32 lowercase hex chars.
TRIP_ID_PATTERN = r"^trip_[0-9a-f]{32}$"
MAX_DAYS = 7
MAX_STOPS_PER_DAY = 30
MAX_STOPS_TOTAL = 120
Pace = Literal["relaxed", "normal", "intensive"]


class LatLon(BaseModel):
    lat: float
    lon: float


class Travelers(BaseModel):
    adults: int = 2
    children: list[int] = Field(default_factory=list)


class WishItem(BaseModel):
    """One user wish in the order it was mentioned.

    kind: "interest" — semantic category search (restaurant, bar, ...);
    kind: "must" — a named must-visit place resolved by name search.
    category: provider taxonomy (attraction/museum/restaurant/cafe/bar/
    park/beach/viewpoint) or None for a free-text query.
    """

    label: str
    kind: str = "interest"
    category: str | None = None
    query: str = ""


class TripIntent(BaseModel):
    destination: str = ""
    days: int = 1
    startTime: str = "10:00"
    endTime: str = "20:00"
    interests: list[str] = Field(default_factory=list)
    wishSequence: list[WishItem] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    travelers: Travelers = Field(default_factory=Travelers)
    transportPreference: TransportMode = "walk"
    budget: float | None = None
    pace: Pace = "normal"
    mustVisit: list[str] = Field(default_factory=list)
    returnBy: str | None = None
    editAction: str | None = None
    editTarget: str | None = None
    # For replace_stop: the "на …" query (new place). editTarget is what to replace.
    editReplacement: str | None = None

    @field_validator("days")
    @classmethod
    def clamp_days(cls, v: int) -> int:
        return max(1, min(int(v), 7))


class Place(BaseModel):
    placeProvider: str
    placeId: str
    name: str
    category: str
    lat: float
    lon: float
    address: str = ""
    description: str = ""
    photoUrl: str | None = None
    rating: float | None = None
    ratingCount: int | None = None
    website: str | None = None
    openingHours: str | None = None
    wikidataId: str | None = None
    # OSM semantic type: suburb|neighbourhood|museum|amenity|tourism|… (empty if unknown).
    placeKind: str = ""


class TravelSegment(BaseModel):
    fromStopId: str
    toStopId: str
    mode: Literal["walk", "car", "transit"]
    distanceMeters: int
    durationSeconds: int
    # False when routing provider failed — never invent haversine as a "real" leg.
    verified: bool = True
    # Encoded OSRM polyline (precision 5) for this leg only; absent when unverified.
    polyline: str | None = None


class Stop(BaseModel):
    id: str
    placeProvider: str
    placeId: str
    name: str
    category: str
    lat: float
    lon: float
    address: str = ""
    startTime: str = ""
    durationMinutes: int = 90
    description: str = ""
    photoUrl: str | None = None
    rating: float | None = None
    ratingCount: int | None = None
    website: str | None = None
    wikidataId: str | None = None


class DayRoute(BaseModel):
    distanceMeters: int = 0
    durationSeconds: int = 0
    polyline: str | None = None
    # False when day totals include unverified legs or routing failed for the day.
    verified: bool = True


class DayPlan(BaseModel):
    dayNumber: int
    date: str | None = None
    summary: str = ""
    stops: list[Stop] = Field(default_factory=list)
    segments: list[TravelSegment] = Field(default_factory=list)
    route: DayRoute = Field(default_factory=DayRoute)
    # True when the day has no confirmed stops (e.g. multi-day pad) — incomplete result.
    incomplete: bool = False


class Destination(BaseModel):
    name: str
    country: str = ""
    lat: float
    lon: float


class HotelContext(BaseModel):
    hotelId: str | None = None
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    city: str | None = None
    country: str | None = None


class Trip(BaseModel):
    id: str
    destination: Destination
    hotel: HotelContext = Field(default_factory=HotelContext)
    days: list[DayPlan] = Field(default_factory=list)
    summary: str = ""
    intent: TripIntent = Field(default_factory=TripIntent)
    createdAt: str
    updatedAt: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class PlanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=config.TRIP_MAX_MESSAGE_CHARS)
    hotel: HotelContext | None = None
    travelers: Travelers | None = None
    # Only an id of a trip already owned by this session may be sent;
    # the API rejects anything else instead of overwriting a foreign route.
    tripId: str | None = Field(default=None, max_length=64)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class RebuildDayRequest(BaseModel):
    dayNumber: int = Field(ge=1, le=MAX_DAYS)
    message: str | None = Field(default=None, max_length=1000)


class TripPatch(BaseModel):
    """Strict PATCH payload: bounded depth and size, unknown keys ignored."""

    model_config = ConfigDict(extra="ignore")

    summary: str | None = Field(default=None, max_length=4000)
    hotel: HotelContext | None = None
    intent: TripIntent | None = None
    days: list[DayPlan] | None = Field(default=None, max_length=MAX_DAYS)

    @field_validator("days")
    @classmethod
    def _bounded_days(cls, value: list[DayPlan] | None) -> list[DayPlan] | None:
        if value is None:
            return value
        if sum(len(day.stops) for day in value) > MAX_STOPS_TOTAL:
            raise ValueError("too many stops")
        for day in value:
            if len(day.stops) > MAX_STOPS_PER_DAY:
                raise ValueError("too many stops in a day")
        return value


class PlacesSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    nearLat: float = Field(ge=-90, le=90)
    nearLon: float = Field(ge=-180, le=180)
    radiusMeters: int = Field(default=5000, ge=50, le=25_000)
    category: str | None = Field(default=None, max_length=40)


class RouteCalculateRequest(BaseModel):
    originLat: float = Field(ge=-90, le=90)
    originLon: float = Field(ge=-180, le=180)
    destLat: float = Field(ge=-90, le=90)
    destLon: float = Field(ge=-180, le=180)
    mode: Literal["walk", "car", "transit"] = "walk"
