from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


TransportMode = Literal["walk", "car", "transit", "mixed"]
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
    message: str
    hotel: HotelContext | None = None
    travelers: Travelers | None = None
    tripId: str | None = None


class ChatRequest(BaseModel):
    message: str


class RebuildDayRequest(BaseModel):
    dayNumber: int
    message: str | None = None


class PlacesSearchRequest(BaseModel):
    query: str
    nearLat: float
    nearLon: float
    radiusMeters: int = 5000
    category: str | None = None


class RouteCalculateRequest(BaseModel):
    originLat: float
    originLon: float
    destLat: float
    destLon: float
    mode: Literal["walk", "car", "transit"] = "walk"
