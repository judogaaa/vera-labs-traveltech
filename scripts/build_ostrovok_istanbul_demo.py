#!/usr/bin/env python3
"""Build Istanbul demo payload for hotel intelligence.

Reads curated hotels.jsonl, writes data/ostrovok_demo/hotels.json (20–30 hotels
with provenance). Optionally enriches with live OSM/OSRM into observations.jsonl
+ cache. Verification status stays honest: geo calcs are estimated, never fake verified.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _is_istanbul(row: dict) -> bool:
    zone = (row.get("zone_key") or "").lower()
    resort = (row.get("resort_area") or "").lower()
    name = (row.get("canonical_name") or "").lower()
    city = (row.get("city") or "")
    if zone == "istanbul":
        return True
    if "istanbul" in resort or "istanbul" in name:
        return True
    # Cyrillic Стамбул often appears in city field
    if "стамбул" in city.lower() or "stanbul" in city.lower():
        return True
    return False


def select_hotels(src: Path, limit: int = 25) -> list[dict]:
    rows: list[dict] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not _is_istanbul(obj):
            continue
        if obj.get("latitude") is None or obj.get("longitude") is None:
            continue
        rows.append(obj)
        if len(rows) >= limit:
            break
    return rows


def to_demo_hotel(row: dict) -> dict:
    sources = []
    for s in row.get("sources") or []:
        sources.append(
            {
                "type": s.get("type"),
                "url": s.get("url"),
                "checked_at": s.get("checked_at"),
            }
        )
    if row.get("official_website"):
        if not any(s.get("url") == row["official_website"] for s in sources):
            sources.append(
                {
                    "type": "official",
                    "url": row["official_website"],
                    "checked_at": row.get("verified_at"),
                }
            )
    if row.get("wikidata_id"):
        wd = f"https://www.wikidata.org/wiki/{row['wikidata_id']}"
        if not any(s.get("url") == wd for s in sources):
            sources.append({"type": "wikidata", "url": wd, "checked_at": row.get("verified_at")})

    return {
        "hotel_id": row["id"],
        "id": row["id"],
        "name": row.get("canonical_name"),
        "canonical_name": row.get("canonical_name"),
        "city": "Istanbul",
        "country_code": row.get("country_code") or "TR",
        "lat": row["latitude"],
        "lon": row["longitude"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "zone_key": "istanbul",
        "official_website": row.get("official_website"),
        "wikidata_id": row.get("wikidata_id"),
        "dataset_matches": row.get("dataset_matches") or [],
        "sources": sources,
        "provenance": {
            "curated_id": row["id"],
            "source_file": "data/curated_hotels/hotels.jsonl",
            "data_quality": row.get("data_quality"),
            "verified_at": row.get("verified_at"),
            "note": "Coordinates and identity from curated catalog; attribute claims require enrichment.",
        },
        "region": "istanbul",
    }


def enrich_live(hotels: list[dict], out_obs: Path, *, limit: int | None = None) -> int:
    from services.hotel_intelligence.calculators.car_access import compute_car_access
    from services.hotel_intelligence.calculators.family_infrastructure import (
        compute_family_infrastructure,
    )
    from services.hotel_intelligence.calculators.night_services import compute_night_services
    from services.hotel_intelligence.calculators.noise_proxy import compute_noise_risk
    from services.hotel_intelligence.calculators.walk_access import compute_walk_to_metro

    calcs = [
        compute_walk_to_metro,
        compute_noise_risk,
        compute_night_services,
        compute_family_infrastructure,
        compute_car_access,
    ]
    count = 0
    target = hotels if limit is None else hotels[:limit]
    with out_obs.open("w", encoding="utf-8") as fh:
        for hotel in target:
            hid = hotel["hotel_id"]
            lat = float(hotel["lat"])
            lon = float(hotel["lon"])
            for calc in calcs:
                try:
                    obs = calc(hid, lat, lon)
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] {hid} {calc.__name__}: {exc}", file=sys.stderr)
                    continue
                # Honesty: never rewrite estimated → verified here
                assert obs.status.value != "verified" or any(
                    s.kind != "hotelier_simulated" for s in obs.sources
                )
                fh.write(obs.model_dump_json() + "\n")
                count += 1
                print(
                    f"  {hid} {obs.attribute_key} → {obs.status.value}",
                    flush=True,
                )
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        type=Path,
        default=ROOT / "data" / "curated_hotels" / "hotels.jsonl",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "data" / "ostrovok_demo",
    )
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Call live OSM/OSRM and write observations.jsonl + cache",
    )
    parser.add_argument(
        "--enrich-limit",
        type=int,
        default=None,
        help="Limit hotels enriched when --enrich is set",
    )
    args = parser.parse_args()

    if not args.src.exists():
        print(f"Missing source: {args.src}", file=sys.stderr)
        return 1

    selected = select_hotels(args.src, limit=args.limit)
    if len(selected) < 20:
        print(
            f"[warn] Only {len(selected)} Istanbul hotels with coordinates found "
            f"(target 20–30).",
            file=sys.stderr,
        )
    demo = [to_demo_hotel(r) for r in selected]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "cache").mkdir(parents=True, exist_ok=True)

    hotels_path = args.out_dir / "hotels.json"
    payload = {
        "region": "istanbul",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(demo),
        "note": (
            "Identity/coords from curated catalog. Attribute observations are "
            "separate; geo methods produce estimated status, never invented verified."
        ),
        "hotels": demo,
    }
    hotels_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(demo)} hotels -> {hotels_path}")

    if args.enrich:
        obs_path = args.out_dir / "observations.jsonl"
        n = enrich_live(demo, obs_path, limit=args.enrich_limit)
        print(f"Wrote {n} observations -> {obs_path}")
    else:
        print("Skipped live enrichment (pass --enrich to fetch OSM/OSRM).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
