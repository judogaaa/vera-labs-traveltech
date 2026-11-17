"""Deterministic providers for unit tests. Never used to invent live itineraries."""

from __future__ import annotations

from ..models import LatLon, Place
from .base import GeocodingProvider, PlacesProvider, ProviderError, RouteResult, RoutingProvider

# Verified real coordinates (OpenStreetMap / public knowledge)
KAZAN_CENTER = LatLon(lat=55.796127, lon=49.106414)
ANTALYA_TEKIROVA = LatLon(lat=36.5058, lon=30.5284)
# City centre near Kaleiçi / Konyaaltı — default Antalya geocode (not Tekirova).
ANTALYA_CENTER = LatLon(lat=36.8969, lon=30.7133)
ISTANBUL_CENTER = LatLon(lat=41.0082, lon=28.9784)
DUBAI_CENTER = LatLon(lat=25.2048, lon=55.2708)
SF_CENTER = LatLon(lat=37.7749, lon=-122.4194)

SF_PLACES = [
    Place(
        placeProvider="fixture",
        placeId="fixture:sf/zuni",
        name="Zuni Café",
        category="restaurant",
        lat=37.7735,
        lon=-122.4216,
        address="1658 Market St, San Francisco",
        description="California cuisine",
        rating=4.6,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:sf/bar",
        name="Trick Dog",
        category="bar",
        lat=37.7590,
        lon=-122.4129,
        address="3010 20th St, San Francisco",
        description="Cocktail bar",
        rating=4.5,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:sf/twin-peaks",
        name="Twin Peaks Viewpoint",
        category="viewpoint",
        lat=37.7544,
        lon=-122.4477,
        address="Twin Peaks Blvd, San Francisco",
        description="Night city panorama",
        rating=4.8,
    ),
]

KAZAN_PLACES = [
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/kremlin",
        name="Казанский Кремль",
        category="attraction",
        lat=55.7984,
        lon=49.1053,
        address="Кремль, Казань",
        description="Историко-архитектурный комплекс — объект ЮНЕСКО",
        rating=4.9,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/kul-sharif",
        name="Мечеть Кул-Шариф",
        category="religious",
        lat=55.7989,
        lon=49.1050,
        address="Кремль, Казань",
        description="Главная соборная мечеть Казанского кремля",
        rating=4.8,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/bauman",
        name="Улица Баумана",
        category="attraction",
        lat=55.7887,
        lon=49.1214,
        address="ул. Баумана, Казань",
        description="Пешеходная улица в центре Казани",
        rating=4.7,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/museum",
        name="Национальный музей Республики Татарстан",
        category="museum",
        lat=55.7963,
        lon=49.1087,
        address="Кремлёвская ул., 2, Казань",
        description="Крупнейший музей Татарстана",
        rating=4.6,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/embankment",
        name="Кремлёвская набережная",
        category="park",
        lat=55.8005,
        lon=49.1020,
        address="Кремлёвская набережная, Казань",
        description="Прогулочная набережная у кремля",
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/restaurant",
        # Real ethno-complex restaurant near the Kremlin (OSM / public listings).
        name="Туган Авылым",
        category="restaurant",
        lat=55.7950,
        lon=49.1120,
        address="ул. Тукая, 2, Казань",
        description="Ресторан татарской кухни, этнокомплекс Туган Авылым",
        rating=4.5,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/cafe-skuratov",
        # Real coffee shop on Bauman Street (OSM amenity=cafe).
        name="Skuratov Coffee",
        category="cafe",
        lat=55.7901,
        lon=49.1218,
        address="ул. Баумана, 9, Казань",
        description="Кофейня Skuratov Coffee на Баумана",
        rating=4.6,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/bar-soyka",
        # Real cocktail bar near Bauman (kept for bar-wish regressions only).
        name="Сойка",
        category="bar",
        lat=55.7898,
        lon=49.1225,
        address="ул. Баумана, 58, Казань",
        description="Бар Сойка",
        rating=4.5,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:kazan/wine-bar",
        name="Винный бар Маяк",
        category="bar",
        lat=55.7910,
        lon=49.1185,
        address="ул. Профсоюзная, Казань",
        description="Винный бар Маяк",
        rating=4.4,
    ),
]

ISTANBUL_PLACES = [
    Place(
        placeProvider="fixture",
        placeId="fixture:istanbul/hagia",
        name="Айя-София",
        category="attraction",
        lat=41.0086,
        lon=28.9802,
        address="Sultan Ahmet, Istanbul",
        description="Историческая мечеть-музей",
        rating=4.9,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:istanbul/blue-mosque",
        name="Голубая мечеть",
        category="religious",
        lat=41.0054,
        lon=28.9768,
        address="Sultan Ahmet, Istanbul",
        description="Султанахмет Blue Mosque",
        rating=4.8,
        wikidataId="Q182170",
        photoUrl="File:Sultan Ahmed Mosque.jpg",
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:istanbul/archaeology",
        name="Археологический музей",
        category="museum",
        lat=41.0115,
        lon=28.9814,
        address="Gülhane, Istanbul",
        description="Музей археологии",
        rating=4.6,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:istanbul/galata",
        name="Галатская башня",
        category="viewpoint",
        lat=41.0256,
        lon=28.9744,
        address="Beyoğlu, Istanbul",
        description="Смотровая башня",
        rating=4.7,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:istanbul/restaurant",
        name="Рыбный ресторан у Босфора",
        category="restaurant",
        lat=41.0405,
        lon=29.0060,
        address="Beşiktaş, Istanbul",
        description="Морепродукты у воды",
        rating=4.6,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:istanbul/cafe",
        name="Kronotrop Karaköy",
        category="cafe",
        lat=41.0232,
        lon=28.9735,
        address="Kemankeş Karamustafa Paşa, Karaköy, Istanbul",
        description="Кофейня Kronotrop в Каракое",
        rating=4.5,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:istanbul/bar",
        name="Unter",
        category="bar",
        lat=41.0335,
        lon=28.9780,
        address="Asmalımescit, Beyoğlu, Istanbul",
        description="Бар Unter",
        rating=4.4,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:istanbul/wine-bar",
        name="Alexandra",
        category="bar",
        lat=41.0240,
        lon=28.9748,
        address="Karaköy, Istanbul",
        description="Коктейль-бар Alexandra",
        rating=4.5,
    ),
]

DUBAI_PLACES = [
    Place(
        placeProvider="fixture",
        placeId="fixture:dubai/burj",
        # Bilingual name so RU/EN wish tokens match Arabic display labels.
        name="برج خليفة · Burj Khalifa",
        category="attraction",
        lat=25.1972,
        lon=55.2744,
        address="1 Sheikh Mohammed bin Rashid Blvd, Dubai",
        description="Burj Khalifa Бурдж-Халифа",
        rating=4.8,
        wikidataId="Q4555",
        photoUrl="File:Burj Khalifa Image.jpg",
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:dubai/dubai-mall",
        name="دبي مول · Dubai Mall",
        category="shopping",
        lat=25.1985,
        lon=55.2796,
        address="Financial Center Rd, Dubai",
        description="The Dubai Mall молл mall шопинг",
        rating=4.7,
        photoUrl="File:13 Dubai Mall night view exterior.jpg",
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:dubai/mosque",
        name="مسجد جميرا · Jumeirah Mosque",
        category="religious",
        lat=25.2335,
        lon=55.2655,
        address="Jumeirah Beach Rd, Dubai",
        description="Jumeirah Mosque мечеть",
        rating=4.8,
        photoUrl="File:Jumeirah Mosque.jpg",
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:dubai/marina",
        name="مرسى دبي · Dubai Marina",
        category="attraction",
        lat=25.0805,
        lon=55.1403,
        address="Dubai Marina",
        description="Dubai Marina waterfront марина",
        rating=4.6,
        photoUrl="File:Dubai Marina Skyline.jpg",
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:dubai/cafe",
        name="مقهى وسط المدينة · Downtown Cafe",
        category="cafe",
        lat=25.2048,
        lon=55.2708,
        address="Downtown Dubai",
        description="Cafe stop downtown кафе",
        rating=4.4,
    ),
]


ANTALYA_PLACES = [
    Place(
        placeProvider="fixture",
        placeId="fixture:antalya/beach",
        name="Пляж Коньяалты",
        category="beach",
        # Konyaaltı — walkable/short hop from Kaleiçi, not Tekirova (~50 km south).
        lat=36.8840,
        lon=30.6355,
        address="Konyaaltı, Antalya",
        description="Городской пляж Коньяалты",
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:antalya/oldtown",
        name="Старый город Калеичи",
        category="attraction",
        lat=36.8854,
        lon=30.7056,
        address="Kaleiçi, Antalya",
        description="Исторический центр Антальи",
        rating=4.7,
    ),
    Place(
        placeProvider="fixture",
        placeId="fixture:antalya/restaurant",
        # Real old-harbour restaurant (OSM / public listings).
        name="Club Arma",
        category="restaurant",
        lat=36.8845,
        lon=30.7048,
        address="Yat Limanı, Kaleiçi, Antalya",
        description="Ресторан Club Arma у старой гавани",
        rating=4.5,
    ),
]


class FixtureGeocodingProvider(GeocodingProvider):
    name = "fixture"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def geocode(self, text: str) -> LatLon | None:
        if self.fail:
            raise ProviderError("geocoding_unavailable", "Fixture geocoder forced failure")
        t = text.lower()
        if "казан" in t or "kazan" in t:
            return KAZAN_CENTER
        if "стамбул" in t or "istanbul" in t:
            return ISTANBUL_CENTER
        if "текиров" in t or "tekirova" in t:
            return ANTALYA_TEKIROVA
        if "антал" in t or "antalya" in t or "коньяалт" in t or "konyaalti" in t:
            return ANTALYA_CENTER
        if "дубай" in t or "dubai" in t:
            return DUBAI_CENTER
        if "франц" in t or "фрациско" in t or "francisco" in t or "san francisco" in t:
            return SF_CENTER
        return None

    def geocode_candidates(self, text: str, limit: int = 5) -> list["GeocodeCandidate"]:
        from .base import GeocodeCandidate

        ll = self.geocode(text)
        if not ll:
            return []
        rev = self.reverse_geocode(ll.lat, ll.lon)
        return [
            GeocodeCandidate(
                lat=ll.lat,
                lon=ll.lon,
                name=rev.get("city") or text,
                city=rev.get("city") or "",
                country=rev.get("country") or "",
                kind="city",
            )
        ]

    def reverse_geocode(self, lat: float, lon: float) -> dict[str, str]:
        if abs(lat - KAZAN_CENTER.lat) < 0.5:
            return {"name": "Казань", "city": "Казань", "country": "Россия", "address": "Казань"}
        if abs(lat - ISTANBUL_CENTER.lat) < 0.5 and abs(lon - ISTANBUL_CENTER.lon) < 0.5:
            return {"name": "Istanbul", "city": "Istanbul", "country": "Türkiye", "address": "Istanbul"}
        if abs(lat - ANTALYA_CENTER.lat) < 0.6 and abs(lon - ANTALYA_CENTER.lon) < 0.6:
            return {"name": "Antalya", "city": "Antalya", "country": "Türkiye", "address": "Antalya"}
        if abs(lat - ANTALYA_TEKIROVA.lat) < 0.35 and abs(lon - ANTALYA_TEKIROVA.lon) < 0.35:
            return {"name": "Tekirova", "city": "Antalya", "country": "Türkiye", "address": "Tekirova"}
        if abs(lat - SF_CENTER.lat) < 0.5 and abs(lon - SF_CENTER.lon) < 0.5:
            return {
                "name": "San Francisco",
                "city": "San Francisco",
                "country": "USA",
                "address": "San Francisco",
            }
        if abs(lat - DUBAI_CENTER.lat) < 0.8 and abs(lon - DUBAI_CENTER.lon) < 0.8:
            return {"name": "دبي", "city": "Dubai", "country": "UAE", "address": "Dubai"}
        return {"name": "", "city": "", "country": "", "address": ""}


class FixturePlacesProvider(PlacesProvider):
    name = "fixture"

    def __init__(self, fail: bool = False, places: list[Place] | None = None) -> None:
        self.fail = fail
        self._places = places or (
            KAZAN_PLACES + ANTALYA_PLACES + ISTANBUL_PLACES + DUBAI_PLACES + SF_PLACES
        )

    def search_places(
        self,
        query: str,
        near: LatLon,
        radius: int = 5000,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Place]:
        if self.fail:
            raise ProviderError("places_unavailable", "Fixture places forced failure")
        q = (query or "").lower()
        cat = (category or "").lower()
        out: list[Place] = []
        for p in self._places:
            dist = ((p.lat - near.lat) ** 2 + (p.lon - near.lon) ** 2) ** 0.5 * 111_000
            if dist > radius * 3:  # generous for fixture city clusters
                # Keep searches city-local: don't mix Kazan / Istanbul / Antalya pools.
                if abs(near.lat - p.lat) > 3.0 or abs(near.lon - p.lon) > 3.0:
                    continue
            if cat and cat not in p.category and cat not in p.name.lower():
                if cat == "attraction" and p.category in {"museum", "religious", "park", "viewpoint"}:
                    pass
                elif cat == "пляж" or cat == "beach":
                    if p.category != "beach":
                        continue
                elif cat in {"ресторан", "restaurant"} and p.category != "restaurant":
                    continue
                elif cat in {"музей", "museum"} and p.category != "museum":
                    continue
                elif cat in {"бар", "bar"} and p.category != "bar":
                    continue
                elif cat in {"кафе", "cafe"} and p.category != "cafe":
                    continue
                elif cat in {"смотровая", "viewpoint"} and p.category != "viewpoint":
                    continue
                else:
                    continue
            hay = f"{p.name} {p.category} {p.description} {p.address}".lower()
            if q and not any(tok in hay for tok in q.split() if len(tok) > 2):
                if not cat:
                    continue
            out.append(p)
            if len(out) >= limit:
                break
        if not out:
            # Nearby fallback — never cross-fill cafe/restaurant/bar with another category.
            ranked = sorted(
                self._places,
                key=lambda p: (p.lat - near.lat) ** 2 + (p.lon - near.lon) ** 2,
            )
            want_cat = {
                "кафе": "cafe",
                "ресторан": "restaurant",
                "бар": "bar",
            }.get(cat, cat)
            for p in ranked:
                if abs(near.lat - p.lat) > 3.0 or abs(near.lon - p.lon) > 3.0:
                    continue
                if want_cat in {"cafe", "restaurant", "bar"} and p.category != want_cat:
                    continue
                out.append(p)
                if len(out) >= limit:
                    break
        return out[:limit]

    def get_place_details(self, place_id: str) -> Place | None:
        for p in self._places:
            if p.placeId == place_id:
                return p
        return None


class FixtureRoutingProvider(RoutingProvider):
    name = "fixture"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def build_route(self, origin: LatLon, destination: LatLon, mode: str = "walk") -> RouteResult:
        if self.fail:
            raise ProviderError("route_unavailable", "Fixture routing forced failure")
        # Haversine-ish meters * walking factor — marked verified only for tests
        import math

        r = 6371000
        p1, p2 = math.radians(origin.lat), math.radians(destination.lat)
        dphi = math.radians(destination.lat - origin.lat)
        dlmb = math.radians(destination.lon - origin.lon)
        a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
        dist = int(2 * r * math.asin(math.sqrt(a)))
        speed = 1.3 if mode == "walk" else 8.0  # m/s
        return RouteResult(
            distanceMeters=dist,
            durationSeconds=int(dist / speed),
            polyline=None,
            mode=mode if mode in {"walk", "car", "transit"} else "walk",
            provider=self.name,
            verified=True,
        )
