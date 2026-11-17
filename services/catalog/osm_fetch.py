"""Fetch hotel nodes from OpenStreetMap Overpass API."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

from .quotas import ZONES

OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "vera-labs-curated-hotels/1.0"


def _query(ql: str, retries: int = 3) -> dict[str, Any]:
    data = urllib.parse.urlencode({"data": ql}).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS,
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(3 + attempt * 3)
    raise RuntimeError(f"Overpass failed: {last_err}")


def fetch_zone_hotels(country_code: str, zone: tuple, limit: int = 80) -> list[dict[str, Any]]:
    zone_key, city_ru, resort_en, south, north, west, east = zone
    ql = f"""
    [out:json][timeout:60];
    (
      node["tourism"="hotel"]({south},{west},{north},{east});
      way["tourism"="hotel"]({south},{west},{north},{east});
    );
    out center tags {limit};
    """
    payload = _query(ql)
    out: list[dict[str, Any]] = []
    for el in payload.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name:en") or tags.get("name") or tags.get("name:ru")
        if not name:
            continue
        if "lat" in el and "lon" in el:
            lat, lon = float(el["lat"]), float(el["lon"])
        else:
            c = el.get("center") or {}
            if "lat" not in c:
                continue
            lat, lon = float(c["lat"]), float(c["lon"])
        stars = None
        if tags.get("stars"):
            try:
                stars = float(str(tags["stars"]).replace("*", "").strip())
            except ValueError:
                stars = None
        out.append(
            {
                "osm_type": el.get("type"),
                "osm_id": el.get("id"),
                "canonical_name": name,
                "official_website": tags.get("website") or tags.get("contact:website"),
                "latitude": lat,
                "longitude": lon,
                "star_rating": stars,
                "brand": tags.get("brand"),
                "country_code": country_code,
                "city": city_ru,
                "resort_area": resort_en,
                "zone_key": zone_key,
                "source": "osm",
            }
        )
    return out


def fetch_for_countries(codes: list[str], per_zone: int = 40) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for cc in codes:
        rows: list[dict[str, Any]] = []
        for zone in ZONES.get(cc, []):
            print(f"[osm] {cc}/{zone[0]}...")
            try:
                rows.extend(fetch_zone_hotels(cc, zone, limit=per_zone))
            except Exception as exc:  # noqa: BLE001
                print(f"[osm] {cc}/{zone[0]} FAILED: {exc}")
            time.sleep(1.5)
        # dedupe by osm id
        seen: set[tuple] = set()
        uniq = []
        for r in rows:
            key = (r.get("osm_type"), r.get("osm_id"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(r)
        result[cc] = uniq
        print(f"[osm] {cc}: {len(uniq)}")
    return result
