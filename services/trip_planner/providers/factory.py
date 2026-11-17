from __future__ import annotations

from .. import config
from .base import GeocodingProvider, PlacesProvider, RoutingProvider
from .nominatim import NominatimGeocodingProvider
from .osrm import OsrmRoutingProvider
from .overpass import OverpassPlacesProvider


def get_geocoding_provider() -> GeocodingProvider:
    name = config.GEOCODING_PROVIDER
    if name == "fixture" and config.ALLOW_FIXTURE_PROVIDERS:
        from .fixtures import FixtureGeocodingProvider

        return FixtureGeocodingProvider()
    return NominatimGeocodingProvider()


def get_places_provider() -> PlacesProvider:
    name = config.PLACES_PROVIDER
    if name == "fixture" and config.ALLOW_FIXTURE_PROVIDERS:
        from .fixtures import FixturePlacesProvider

        return FixturePlacesProvider()
    if name == "nominatim":
        from .nominatim_places import NominatimPlacesProvider

        return NominatimPlacesProvider()
    # Default: Overpass with Nominatim fallback (verified OSM only)
    from .nominatim_places import FallbackPlacesProvider, NominatimPlacesProvider

    return FallbackPlacesProvider(OverpassPlacesProvider(), NominatimPlacesProvider())


def get_routing_provider() -> RoutingProvider:
    name = config.ROUTING_PROVIDER
    if name == "fixture" and config.ALLOW_FIXTURE_PROVIDERS:
        from .fixtures import FixtureRoutingProvider

        return FixtureRoutingProvider()
    return OsrmRoutingProvider()


def provider_status() -> dict[str, str]:
    from services.ai import gigachat_config as gc

    places = get_places_provider()
    return {
        "geocoding": get_geocoding_provider().name,
        "places": places.name,
        "routing": get_routing_provider().name,
        "gigachat": (
            "enabled"
            if gc.GIGACHAT_ENABLED and gc.GIGACHAT_AUTH_KEY
            else "disabled_or_missing_key"
        ),
        "gigachatScope": gc.GIGACHAT_SCOPE,
        "gigachatModel": gc.GIGACHAT_MODEL or "(auto)",
        "mapTiles": "openfreemap-vector",
    }
