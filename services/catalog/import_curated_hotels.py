"""
Import curated hotels.jsonl into a local JSON store used by the catalog API.

Usage:
  python -m services.catalog.import_curated_hotels
  python -m services.catalog.import_curated_hotels --src data/curated_hotels/hotels.jsonl
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = ROOT / "data" / "curated_hotels" / "hotels.jsonl"
DEFAULT_DST = ROOT / "data" / "curated_hotels" / "catalog_db.json"
SLIM_DST = ROOT / "src" / "data" / "curatedHotelsSlim.json"
# Runtime fetch path for the Vite app (avoid bundling 1.6MB JSON into JS).
PUBLIC_SLIM_DST = ROOT / "public" / "data" / "curatedHotelsSlim.json"


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def to_slim(hotel: dict) -> dict:
    images = hotel.get("images") or []
    display_urls = [
        img["source_url"]
        for img in images
        if img.get("source_url") and img.get("usage_status") in {"index_allowed", "display_allowed", "reference_only"}
    ][:8]
    return {
        "id": hotel["id"],
        "name": hotel["canonical_name"],
        "chain": hotel.get("brand") or hotel.get("chain"),
        "latitude": hotel.get("latitude"),
        "longitude": hotel.get("longitude"),
        "images": display_urls,
        "provider": "curated",
        "image_count": len(images),
        "city": hotel.get("city"),
        "country": hotel.get("country"),
        "country_code": hotel.get("country_code"),
        "resort_area": hotel.get("resort_area"),
        "description": hotel.get("description_ru"),
        "amenities": hotel.get("amenities") or hotel.get("categories") or [],
        "rating": None,
        "reviewCount": None,
        "pricePerNight": (hotel.get("price") or {}).get("amount"),
        "price_status": (hotel.get("price") or {}).get("status", "unavailable"),
        "price_currency": (hotel.get("price") or {}).get("currency"),
        "price_note": (hotel.get("price") or {}).get("note"),
        "curation_score": hotel.get("curation_score"),
        "data_quality": hotel.get("data_quality"),
        "official_website": hotel.get("official_website"),
        "source": "curated",
    }


def import_catalog(src: Path, dst: Path, slim: Path) -> dict:
    hotels = load_jsonl(src)
    by_id = {h["id"]: h for h in hotels}
    name_index: dict[str, list[str]] = {}
    for h in hotels:
        keys = [h["canonical_name"], *(h.get("aliases") or []), h.get("brand") or "", h.get("city") or ""]
        for k in keys:
            if not k:
                continue
            name_index.setdefault(k.lower(), []).append(h["id"])

    crosswalk_path = src.parent / "dataset_crosswalk.jsonl"
    crosswalk: dict[str, list[dict]] = {}
    if crosswalk_path.exists():
        with crosswalk_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                ds = row.get("dataset")
                ds_id = str(row.get("dataset_hotel_id") or "")
                if not ds or not ds_id:
                    continue
                crosswalk.setdefault(f"{ds}:{ds_id}", []).append(
                    {
                        "hotel_id": row["hotel_id"],
                        "confidence": row.get("confidence"),
                        "matched_by": row.get("matched_by"),
                    }
                )

    db = {
        "version": 1,
        "imported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "count": len(hotels),
        "hotels": hotels,
        "by_id": {hid: i for i, hid in enumerate(by_id)},
        "name_index": name_index,
        "crosswalk": crosswalk,
    }
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")

    slim_rows = [to_slim(h) for h in hotels]
    slim_json = json.dumps(slim_rows, ensure_ascii=False)
    slim.parent.mkdir(parents=True, exist_ok=True)
    slim.write_text(slim_json, encoding="utf-8")
    PUBLIC_SLIM_DST.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_SLIM_DST.write_text(slim_json, encoding="utf-8")

    return {
        "count": len(hotels),
        "dst": str(dst),
        "slim": str(slim),
        "public_slim": str(PUBLIC_SLIM_DST),
        "bytes": dst.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--dst", type=Path, default=DEFAULT_DST)
    parser.add_argument("--slim", type=Path, default=SLIM_DST)
    args = parser.parse_args()
    if not args.src.exists():
        raise SystemExit(f"Missing source: {args.src}")
    stats = import_catalog(args.src, args.dst, args.slim)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
