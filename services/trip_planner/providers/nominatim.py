from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

from .. import config
from ..models import LatLon
from .base import GeocodingProvider, ProviderError

if TYPE_CHECKING:
    from .base import GeocodeCandidate


class NominatimGeocodingProvider(GeocodingProvider):
    name = "nominatim"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=config.HTTP_TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
        self._last_call = 0.0
        # Prefer Russian place names so destinations read naturally in the UI.
        self._lang = {"accept-language": "ru,en"}

    def _throttle(self) -> None:
        # Nominatim usage policy: max 1 req/s
        elapsed = time.monotonic() - self._last_call
        if elapsed < 1.05:
            time.sleep(1.05 - elapsed)
        self._last_call = time.monotonic()

    def geocode(self, text: str) -> LatLon | None:
        q = (text or "").strip()
        if not q:
            return None
        last_err: Exception | None = None
        for _ in range(2):
            self._throttle()
            try:
                resp = self._client.get(
                    f"{config.NOMINATIM_URL}/search",
                    params={"q": q, "format": "json", "limit": 1, **self._lang},
                )
                resp.raise_for_status()
                data: list[dict[str, Any]] = resp.json()
                if not data:
                    return None
                return LatLon(lat=float(data[0]["lat"]), lon=float(data[0]["lon"]))
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        raise ProviderError("geocoding_unavailable", f"Nominatim geocode failed: {last_err}") from last_err

    def geocode_candidates(self, text: str, limit: int = 5) -> list["GeocodeCandidate"]:
        from .base import GeocodeCandidate

        q = (text or "").strip()
        if not q:
            return []
        self._throttle()
        try:
            resp = self._client.get(
                f"{config.NOMINATIM_URL}/search",
                params={
                    "q": q,
                    "format": "json",
                    "limit": max(1, min(limit, 5)),
                    "addressdetails": 1,
                    **self._lang,
                },
            )
            resp.raise_for_status()
            data: list[dict[str, Any]] = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("geocoding_unavailable", f"Nominatim search failed: {exc}") from exc
        out: list[GeocodeCandidate] = []
        for row in data:
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            addr = row.get("address") or {}
            cls = str(row.get("class") or "").lower()
            typ = str(row.get("type") or "").lower()
            if cls == "place":
                kind = "city"
            elif typ == "country":
                kind = "country"
            elif cls == "boundary":
                kind = "admin"
            else:
                kind = ""
            out.append(
                GeocodeCandidate(
                    lat=lat,
                    lon=lon,
                    name=str(row.get("name") or (row.get("display_name") or "").split(",")[0]),
                    city=str(
                        addr.get("city") or addr.get("town") or addr.get("village")
                        or addr.get("municipality") or addr.get("county") or ""
                    ),
                    country=str(addr.get("country") or ""),
                    address=str(row.get("display_name") or ""),
                    kind=kind,
                    importance=float(row.get("importance") or 0.0),
                )
            )
        return out

    def reverse_geocode(self, lat: float, lon: float) -> dict[str, str]:
        self._throttle()
        try:
            resp = self._client.get(
                f"{config.NOMINATIM_URL}/reverse",
                params={"lat": lat, "lon": lon, "format": "json", **self._lang},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("geocoding_unavailable", f"Nominatim reverse failed: {exc}") from exc
        addr = data.get("address") or {}
        return {
            "name": data.get("name") or data.get("display_name", ""),
            "city": addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or "",
            "country": addr.get("country") or "",
            "address": data.get("display_name") or "",
        }
