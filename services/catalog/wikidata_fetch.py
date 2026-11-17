"""Fetch hotel candidates from Wikidata SPARQL (legitimate public API)."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

from .quotas import COUNTRY_META

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "vera-labs-curated-hotels/1.0 (research; contact: local-dev)"


def _query(sparql: str, retries: int = 3) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"{ENDPOINT}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"})
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            rows = []
            for b in payload.get("results", {}).get("bindings", []):
                rows.append({k: v.get("value") for k, v in b.items()})
            return rows
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"Wikidata SPARQL failed: {last_err}")


def fetch_hotels_for_country(country_code: str, limit: int = 500) -> list[dict[str, Any]]:
    meta = COUNTRY_META[country_code]
    wd_id = meta["wd"]
    # Prefer exact hotel/resort types (avoid heavy P279* scans that time out)
    sparql = f"""
    SELECT DISTINCT ?hotel ?hotelLabel ?website ?coord ?adminLabel ?stars WHERE {{
      VALUES ?type {{ wd:Q27686 wd:Q163911 }}
      ?hotel wdt:P31 ?type ;
             wdt:P17 wd:{wd_id} .
      OPTIONAL {{ ?hotel wdt:P856 ?website . }}
      OPTIONAL {{ ?hotel wdt:P625 ?coord . }}
      OPTIONAL {{ ?hotel wdt:P131 ?admin . }}
      OPTIONAL {{ ?hotel wdt:P3487 ?stars . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,ru". }}
    }}
    LIMIT {limit}
    """
    try:
        rows = _query(sparql)
    except Exception as exc:  # noqa: BLE001
        print(f"[wikidata] {country_code} primary query failed ({exc}); trying minimal...")
        sparql_min = f"""
        SELECT DISTINCT ?hotel ?hotelLabel ?website ?coord WHERE {{
          ?hotel wdt:P31 wd:Q27686 ; wdt:P17 wd:{wd_id} .
          OPTIONAL {{ ?hotel wdt:P856 ?website . }}
          OPTIONAL {{ ?hotel wdt:P625 ?coord . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT {min(limit, 200)}
        """
        rows = _query(sparql_min)
    out: list[dict[str, Any]] = []
    for r in rows:
        lat = lon = None
        coord = r.get("coord") or ""
        if coord.startswith("Point("):
            # Point(lon lat)
            try:
                body = coord[len("Point(") : -1]
                lon_s, lat_s = body.split()
                lon, lat = float(lon_s), float(lat_s)
            except ValueError:
                lat = lon = None
        stars = None
        if r.get("stars"):
            try:
                stars = float(r["stars"])
            except ValueError:
                stars = None
        name = (r.get("hotelLabel") or "").strip()
        if not name or name.startswith("Q"):
            continue
        out.append(
            {
                "wikidata_id": (r.get("hotel") or "").rsplit("/", 1)[-1],
                "canonical_name": name,
                "official_website": r.get("website"),
                "latitude": lat,
                "longitude": lon,
                "admin_label": r.get("adminLabel"),
                "star_rating": stars,
                "country_code": country_code,
                "source": "wikidata",
            }
        )
    return out


def fetch_all_countries(codes: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    codes = codes or list(COUNTRY_META.keys())
    result: dict[str, list[dict[str, Any]]] = {}
    for cc in codes:
        print(f"[wikidata] fetching {cc}...")
        try:
            rows = fetch_hotels_for_country(cc)
            print(f"[wikidata] {cc}: {len(rows)} hotels")
            result[cc] = rows
        except Exception as exc:  # noqa: BLE001
            print(f"[wikidata] {cc} FAILED: {exc}")
            result[cc] = []
        time.sleep(1.2)
    return result
