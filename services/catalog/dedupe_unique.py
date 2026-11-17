"""
Dedupe curated catalog names and enforce globally unique image URLs.

Sources for replacements (never invent):
  - Hotels-50K (expanded country bboxes, uniquely-owned URLs only)
  - regionHotelsCatalog.json (travelapi covers)
  - ICONIC_SEEDS + Commons / Wikidata images
  - Wikidata hotels with P18

Keeps exact country quotas (1000) and AE Dubai >= 90.
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.catalog.build_fast import (  # noqa: E402
    BATHROOM_RE,
    cover_score,
    describe_ru,
    estimate_price,
    infer_categories,
    order_images,
    rewrite_jsonl,
    utc_now,
)
from services.catalog.hotels50k_index import (  # noqa: E402
    _norm,
    load_chains,
    name_match_score,
    zone_for,
)
from services.catalog.import_curated_hotels import import_catalog  # noqa: E402
from services.catalog.quotas import (  # noqa: E402
    AE_DUBAI_MIN,
    COUNTRY_META,
    ICONIC_SEEDS,
    QUOTAS,
)

OUT = ROOT / "data" / "curated_hotels"
TRAIN = ROOT / "services" / "indexer" / "data" / "hotels50k" / "train_set.csv"
HOTEL_INFO = ROOT / "services" / "indexer" / "data" / "hotels50k" / "hotel_info.csv"
MIN_IMAGES = 1
MAX_IMAGES = 8
TARGET_IMAGES = 2

# Non-overlapping country boxes (list of min_lat, max_lat, min_lon, max_lon).
# More specific / smaller countries listed first when scanning.
COUNTRY_BBOXES: dict[str, list[tuple[float, float, float, float]]] = {
    "SG": [(1.15, 1.48, 103.6, 104.1)],
    "MV": [(-1.0, 8.0, 72.0, 74.0)],
    "SC": [(-5.0, -3.5, 55.2, 56.0)],
    "QA": [(24.4, 26.2, 50.7, 51.75)],
    "AM": [(38.8, 41.4, 43.4, 46.7)],
    "GE": [(41.0, 43.6, 39.5, 46.8)],
    "CU": [(19.5, 23.5, -85.0, -74.0)],
    "LK": [(5.8, 10.0, 79.5, 82.0)],
    "TN": [(30.0, 37.5, 7.5, 12.0)],
    # UAE after Qatar; stop before Oman Gulf of Oman coast
    "AE": [(22.5, 26.5, 51.75, 56.45)],
    # Oman: Muscat/Batinah + Salalah (exclude UAE)
    "OM": [(23.0, 26.5, 56.45, 60.0), (16.5, 18.5, 53.5, 55.5)],
    "EG": [(22.0, 32.0, 24.0, 37.0)],
    "GR": [(34.5, 41.5, 19.0, 28.5)],
    "TR": [(36.0, 42.5, 26.0, 45.0)],
    "TH": [(5.5, 20.5, 97.0, 105.5)],
    "VN": [(8.0, 23.5, 102.0, 110.5)],
    "CN": [(18.0, 41.5, 108.0, 123.0)],
    "ID": [(-9.5, -5.5, 105.0, 119.0)],
}


def norm_name(s: str) -> str:
    return _norm(s or "")


def is_dubai(h: dict) -> bool:
    if h.get("zone_key") == "dubai":
        return True
    city = str(h.get("city") or "").lower()
    return city in {"дубай", "dubai"} or "dubai" in city


def img_urls(h: dict) -> list[str]:
    out = []
    for img in h.get("images") or []:
        u = img.get("source_url") if isinstance(img, dict) else img
        if u:
            out.append(u)
    return out


def make_image_objs(hotel_id: str, urls: list[str], source_type: str = "dataset") -> list[dict]:
    cats = ["exterior", "room", "pool", "beach", "lobby", "view", "restaurant", "other"]
    usage = "index_allowed" if source_type == "dataset" else "display_allowed"
    images = []
    for i, url in enumerate(urls[:MAX_IMAGES]):
        images.append(
            {
                "id": f"{hotel_id}-img-{i+1:02d}",
                "hotel_id": hotel_id,
                "category": cats[i % len(cats)],
                "source_url": url,
                "source_page": None,
                "source_type": source_type,
                "width": None,
                "height": None,
                "usage_status": usage,
                "local_path": None,
            }
        )
    return images


def assign_unused_urls(
    candidate_urls: list[str],
    used_urls: set[str],
    min_n: int = MIN_IMAGES,
    max_n: int = MAX_IMAGES,
) -> list[str] | None:
    picked = []
    for u in candidate_urls:
        if not u or u in used_urls:
            continue
        if cover_score(u) < -50:
            continue
        picked.append(u)
        if len(picked) >= max_n:
            break
    if len(picked) < min_n:
        return None
    return picked


def scan_polluted() -> set[str]:
    url_owners: dict[str, set[str]] = defaultdict(set)
    with TRAIN.open("r", encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            hid, url = row[1].strip(), row[2].strip()
            if url.startswith("http"):
                url_owners[url].add(hid)
    return {u for u, ids in url_owners.items() if len(ids) > 1}


def collect_unique_images(hotel_ids: set[str], polluted: set[str], max_per: int = 12) -> dict[str, list[str]]:
    per: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    remaining = set(hotel_ids)
    if not remaining:
        return {}
    with TRAIN.open("r", encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            hid, url = row[1].strip(), row[2].strip()
            if hid not in remaining:
                continue
            if not url.startswith("http") or url in polluted:
                continue
            if BATHROOM_RE.search(url):
                continue
            if url in seen[hid]:
                continue
            seen[hid].add(url)
            per[hid].append(url)
            if len(per[hid]) >= max_per:
                remaining.discard(hid)
                if not remaining:
                    break
    return {hid: order_images(urls) for hid, urls in per.items()}


def load_h50k_by_bbox() -> dict[str, list[dict]]:
    chains = load_chains()
    by_cc: dict[str, list[dict]] = defaultdict(list)
    # preserve insertion order (specific first)
    ordered = list(COUNTRY_BBOXES.items())
    with HOTEL_INFO.open("r", encoding="utf-8", newline="") as f:
        next(csv.reader(f), None)
        for row in csv.reader(f):
            if len(row) < 5:
                continue
            hid = row[0].strip()
            name = row[1].strip()
            chain_id = row[2].strip()
            try:
                lat = float(row[3]) if row[3].strip() else None
                lon = float(row[4]) if row[4].strip() else None
            except ValueError:
                continue
            if lat is None or lon is None:
                continue
            matched_cc = None
            for cc, boxes in ordered:
                for a, b, c, d in boxes:
                    if a <= lat <= b and c <= lon <= d:
                        matched_cc = cc
                        break
                if matched_cc:
                    break
            if not matched_cc or matched_cc not in QUOTAS:
                continue
            z = zone_for(matched_cc, lat, lon)
            zone_key = z[0] if z else None
            city = z[1] if z else COUNTRY_META[matched_cc]["name_ru"]
            resort = z[2] if z else city
            brand = chains.get(chain_id)
            if brand and brand.lower() == "unknown":
                brand = None
            by_cc[matched_cc].append(
                {
                    "dataset_hotel_id": hid,
                    "canonical_name": name,
                    "brand": brand,
                    "chain": chains.get(chain_id),
                    "latitude": lat,
                    "longitude": lon,
                    "country_code": matched_cc,
                    "city": city,
                    "resort_area": resort,
                    "zone_key": zone_key,
                    "source": "hotels50k",
                    "_score": 62 + (8 if brand else 0),
                }
            )
    return dict(by_cc)


def load_region_candidates() -> dict[str, list[dict]]:
    path = ROOT / "src" / "data" / "regionHotelsCatalog.json"
    if not path.exists():
        return {}
    ru_to_cc = {m["name_ru"]: cc for cc, m in COUNTRY_META.items()}
    by_cc: dict[str, list[dict]] = defaultdict(list)
    for row in json.loads(path.read_text(encoding="utf-8")):
        cc = ru_to_cc.get(row.get("country") or "")
        if not cc:
            continue
        imgs = order_images(
            [u for u in (row.get("images") or []) if isinstance(u, str) and u.startswith("http")]
        )
        if len(imgs) < TARGET_IMAGES:
            continue
        if not row.get("city") or not row.get("name"):
            continue
        sid = str(row.get("source_hotel_id") or "").replace("h50k-", "") or None
        if not sid and str(row.get("id", "")).startswith("h50k-"):
            sid = str(row["id"]).replace("h50k-", "")
        by_cc[cc].append(
            {
                "dataset_hotel_id": sid,
                "canonical_name": row["name"],
                "brand": row.get("chain"),
                "chain": row.get("chain"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "country_code": cc,
                "city": row["city"],
                "resort_area": row["city"],
                "zone_key": "dubai" if "дубай" in str(row["city"]).lower() or "dubai" in str(row["city"]).lower() else None,
                "source": "region",
                "image_urls": imgs,
                "_score": 75,
            }
        )
    return dict(by_cc)


def load_wikidata_candidates() -> dict[str, list[dict]]:
    path = OUT / "cache" / "wikidata_with_images.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    by_cc: dict[str, list[dict]] = defaultdict(list)
    for cc, rows in raw.items():
        if cc not in QUOTAS:
            continue
        for r in rows:
            urls = [u for u in (r.get("image_urls") or []) if u]
            if not urls or not r.get("canonical_name"):
                continue
            city = COUNTRY_META[cc]["name_ru"]
            z = None
            if r.get("latitude") is not None and r.get("longitude") is not None:
                z = zone_for(cc, float(r["latitude"]), float(r["longitude"]))
            by_cc[cc].append(
                {
                    "canonical_name": r["canonical_name"],
                    "official_website": r.get("official_website"),
                    "latitude": r.get("latitude"),
                    "longitude": r.get("longitude"),
                    "country_code": cc,
                    "city": z[1] if z else city,
                    "resort_area": z[2] if z else city,
                    "zone_key": z[0] if z else None,
                    "wikidata_id": r.get("wikidata_id"),
                    "source": "wikidata",
                    "image_urls": urls,
                    "_score": 72 if r.get("official_website") else 65,
                }
            )
    return dict(by_cc)


def load_seed_commons() -> dict[str, list[str]]:
    path = OUT / "cache" / "seed_commons_images.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def materialize_candidate(c: dict, seq: int, urls: list[str], source_type: str) -> dict:
    hid = f"oh-curated-{seq:06d}"
    cc = c["country_code"]
    meta = COUNTRY_META[cc]
    cats = infer_categories(c["canonical_name"], c.get("resort_area"))
    sources = []
    if c.get("dataset_hotel_id"):
        sources.append(
            {
                "type": "hotels50k",
                "url": f"dataset:hotels50k:{c['dataset_hotel_id']}",
                "checked_at": utc_now(),
            }
        )
    if c.get("official_website"):
        sources.append({"type": "official", "url": c["official_website"], "checked_at": utc_now()})
    if c.get("wikidata_id"):
        sources.append(
            {
                "type": "wikidata",
                "url": f"https://www.wikidata.org/wiki/{c['wikidata_id']}",
                "checked_at": utc_now(),
            }
        )
    if c.get("source") == "iconic_seed" and c.get("official_website"):
        sources.append({"type": "iconic_seed", "url": c["official_website"], "checked_at": utc_now()})

    rec = {
        "id": hid,
        "canonical_name": c["canonical_name"],
        "aliases": [],
        "brand": c.get("brand"),
        "chain": c.get("chain") if c.get("chain") not in (None, "unknown") else c.get("brand"),
        "country": meta["name_ru"],
        "country_code": cc,
        "city": c.get("city") or c.get("resort_area") or meta["name_ru"],
        "resort_area": c.get("resort_area"),
        "latitude": c.get("latitude"),
        "longitude": c.get("longitude"),
        "star_rating": c.get("star_rating"),
        "review_signals": [],
        "awards": [],
        "categories": cats,
        "amenities": c.get("amenities") or [],
        "beach": None,
        "pools": None,
        "family_friendly": None,
        "adults_only": None,
        "all_inclusive": "all_inclusive" in cats,
        "room_types": [],
        "official_website": c.get("official_website"),
        "official_booking_url": None,
        "description_ru": "",
        "highlights_ru": [f"Район: {c.get('resort_area') or c.get('city') or meta['name_ru']}"],
        "curation_score": int(c.get("_score") or 70),
        "curation_reasons": [
            "high-demand Russian leisure destination",
            "multiple image refs" if len(urls) >= 2 else "cover image",
        ],
        "price": {},
        "images": make_image_objs(hid, urls, source_type=source_type),
        "sources": sources,
        "dataset_matches": [],
        "wikidata_id": c.get("wikidata_id"),
        "zone_key": c.get("zone_key"),
        "verified_at": utc_now(),
        "data_quality": "B",
    }
    if c.get("dataset_hotel_id"):
        rec["dataset_matches"] = [
            {
                "dataset": "hotels50k",
                "dataset_hotel_id": str(c["dataset_hotel_id"]),
                "confidence": float(c.get("match_confidence") or 0.9),
                "matched_by": ["name", "coordinates", "city"],
            }
        ]
        rec["curation_reasons"].append("Hotels-50K crosswalk")
    if c.get("official_website"):
        rec["curation_reasons"].append("official website")
    rec["description_ru"] = describe_ru(rec)
    rec["price"] = estimate_price(rec)
    if len(urls) >= 5 and rec.get("official_website") and rec.get("latitude") is not None:
        rec["data_quality"] = "A"
        rec["curation_score"] = max(rec["curation_score"], 85)
    return rec


def h50k_id(h: dict) -> str | None:
    for m in h.get("dataset_matches") or []:
        if m.get("dataset") == "hotels50k":
            return str(m["dataset_hotel_id"])
    return None


def rewrite_side_files(hotels: list[dict]) -> None:
    images_all, sources_all, crosswalk, prices = [], [], [], []
    for h in hotels:
        images_all.extend(h.get("images") or [])
        for s in h.get("sources") or []:
            sources_all.append({"hotel_id": h["id"], **s})
        for m in h.get("dataset_matches") or []:
            crosswalk.append({"hotel_id": h["id"], "canonical_name": h["canonical_name"], **m})
        prices.append({"hotel_id": h["id"], **(h.get("price") or {})})
    rewrite_jsonl(OUT / "image_manifest.jsonl", images_all)
    rewrite_jsonl(OUT / "sources.jsonl", sources_all)
    rewrite_jsonl(OUT / "dataset_crosswalk.jsonl", crosswalk)
    rewrite_jsonl(OUT / "price_snapshots.jsonl", prices)

    with (OUT / "hotels.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "id", "canonical_name", "country_code", "country", "city", "resort_area",
            "latitude", "longitude", "star_rating", "brand", "chain", "official_website",
            "curation_score", "data_quality", "price_status", "price_amount",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for h in hotels:
            w.writerow(
                {
                    "id": h["id"],
                    "canonical_name": h["canonical_name"],
                    "country_code": h["country_code"],
                    "country": h["country"],
                    "city": h["city"],
                    "resort_area": h.get("resort_area"),
                    "latitude": h.get("latitude"),
                    "longitude": h.get("longitude"),
                    "star_rating": h.get("star_rating"),
                    "brand": h.get("brand"),
                    "chain": h.get("chain"),
                    "official_website": h.get("official_website"),
                    "curation_score": h.get("curation_score"),
                    "data_quality": h.get("data_quality"),
                    "price_status": (h.get("price") or {}).get("status"),
                    "price_amount": (h.get("price") or {}).get("amount"),
                }
            )


def assert_unique(hotels: list[dict]) -> dict:
    exact = Counter((h["canonical_name"] or "").strip().lower() for h in hotels)
    names = Counter(norm_name(h["canonical_name"]) for h in hotels)
    url_owners: dict[str, set[str]] = defaultdict(set)
    cover_owners: dict[str, set[str]] = defaultdict(set)
    for h in hotels:
        urls = img_urls(h)
        if not urls:
            continue
        cover_owners[urls[0]].add(h["id"])
        for u in urls:
            url_owners[u].add(h["id"])
    return {
        "exact_dups": sum(1 for v in exact.values() if v > 1),
        "name_dups": sum(1 for k, v in names.items() if v > 1 and k),
        "url_dups": sum(1 for v in url_owners.values() if len(v) > 1),
        "cover_dups": sum(1 for v in cover_owners.values() if len(v) > 1),
        "no_cover": sum(1 for h in hotels if not img_urls(h)),
        "count": len(hotels),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    hotels = [
        json.loads(l)
        for l in (OUT / "hotels.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    print(f"Loaded {len(hotels)}", flush=True)

    stats = {
        "name_near_removed": 0,
        "h50k_collision_cleared": 0,
        "images_reassigned": 0,
        "hotels_replaced": 0,
        "kept_with_unique_imgs": 0,
    }

    # Near-dup names
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for h in hotels:
        by_key[(norm_name(h["canonical_name"]), (h.get("city") or "").lower(), h["country_code"])].append(h)
    drop_ids: set[str] = set()
    for group in by_key.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: (-(x.get("curation_score") or 0), x["id"]))
        for loser in group[1:]:
            drop_ids.add(loser["id"])
            stats["name_near_removed"] += 1
            print(f"  DROP near-dup {loser['canonical_name']}", flush=True)
    hotels = [h for h in hotels if h["id"] not in drop_ids]

    print("Loading pools...", flush=True)
    pool_h50k = load_h50k_by_bbox()
    pool_region = load_region_candidates()
    pool_wd = load_wikidata_candidates()
    seed_commons = load_seed_commons()
    print(
        "  h50k", {cc: len(v) for cc, v in sorted(pool_h50k.items())},
        flush=True,
    )
    print(
        "  region", {cc: len(v) for cc, v in sorted(pool_region.items())},
        flush=True,
    )
    print(
        "  wikidata", {cc: len(v) for cc, v in sorted(pool_wd.items())},
        flush=True,
    )
    print(f"  seed_commons keys={len(seed_commons)}", flush=True)

    h50k_name = {
        str(r["dataset_hotel_id"]): r["canonical_name"]
        for rows in pool_h50k.values()
        for r in rows
    }

    # H50K id collisions
    by_ds: dict[str, list[dict]] = defaultdict(list)
    for h in hotels:
        ds = h50k_id(h)
        if ds:
            by_ds[ds].append(h)
    for ds, group in by_ds.items():
        if len(group) < 2:
            continue
        true_name = h50k_name.get(ds, "")
        group.sort(
            key=lambda h: (
                -name_match_score(h["canonical_name"], true_name) if true_name else 0,
                -(h.get("curation_score") or 0),
                h["id"],
            )
        )
        for loser in group[1:]:
            loser["dataset_matches"] = [
                m for m in (loser.get("dataset_matches") or []) if m.get("dataset") != "hotels50k"
            ]
            loser["images"] = []
            stats["h50k_collision_cleared"] += 1

    print("Scanning polluted URLs...", flush=True)
    polluted = scan_polluted()
    print(f"  polluted={len(polluted)}", flush=True)

    needed_ids = {h50k_id(h) for h in hotels if h50k_id(h)}
    needed_ids |= {str(r["dataset_hotel_id"]) for rows in pool_h50k.values() for r in rows}
    needed_ids |= {
        str(r["dataset_hotel_id"])
        for rows in pool_region.values()
        for r in rows
        if r.get("dataset_hotel_id")
    }
    needed_ids.discard(None)
    print(f"Loading unique images for {len(needed_ids)} ids...", flush=True)
    image_map = collect_unique_images(needed_ids, polluted, max_per=12)
    print(f"  image_map={len(image_map)}", flush=True)

    used_urls: set[str] = set()
    used_names: set[str] = set()
    used_ds: set[str] = set()
    kept: list[dict] = []

    def take(urls: list[str], min_n: int = MIN_IMAGES) -> list[str] | None:
        picked = assign_unused_urls(urls, used_urls, min_n=min_n)
        if not picked:
            return None
        used_urls.update(picked)
        return picked

    def hotel_priority(h: dict) -> tuple:
        urls = [u for u in img_urls(h) if u not in polluted]
        return (-(h.get("curation_score") or 0), -len(urls), h["id"])

    remaining: list[dict] = []
    for h in sorted(hotels, key=hotel_priority):
        nn = norm_name(h["canonical_name"])
        if nn in used_names:
            remaining.append(h)
            continue
        urls = [u for u in img_urls(h) if u not in polluted]
        picked = assign_unused_urls(urls, used_urls, min_n=MIN_IMAGES)
        if picked:
            h = dict(h)
            h["images"] = make_image_objs(h["id"], picked)
            used_urls.update(picked)
            used_names.add(nn)
            ds = h50k_id(h)
            if ds:
                used_ds.add(ds)
            kept.append(h)
            stats["kept_with_unique_imgs"] += 1
        else:
            remaining.append(h)
    print(f"Pass A kept={len(kept)} remaining={len(remaining)}", flush=True)

    still: list[dict] = []
    for h in remaining:
        nn = norm_name(h["canonical_name"])
        if nn in used_names:
            still.append(h)
            continue
        candidates: list[str] = []
        ds = h50k_id(h)
        source_type = "dataset"
        if ds and ds not in used_ds and ds in image_map:
            candidates = image_map[ds]
        # region name match
        if assign_unused_urls(candidates, used_urls) is None:
            for r in pool_region.get(h["country_code"], []):
                if norm_name(r["canonical_name"]) == nn and assign_unused_urls(r.get("image_urls") or [], used_urls):
                    candidates = r["image_urls"]
                    source_type = "travelapi"
                    if r.get("dataset_hotel_id"):
                        ds = str(r["dataset_hotel_id"])
                    break
        # rematch H50K by name
        if assign_unused_urls(candidates, used_urls) is None:
            best = None
            best_sc = 0.0
            for r in pool_h50k.get(h["country_code"], []):
                rid = str(r["dataset_hotel_id"])
                if rid in used_ds or rid not in image_map:
                    continue
                sc = name_match_score(h["canonical_name"], r["canonical_name"])
                if sc < 0.8:
                    continue
                if assign_unused_urls(image_map[rid], used_urls) is None:
                    continue
                if sc > best_sc:
                    best_sc, best = sc, r
            if best:
                ds = str(best["dataset_hotel_id"])
                candidates = image_map[ds]
                source_type = "dataset"
                h = dict(h)
                h["dataset_matches"] = [
                    {
                        "dataset": "hotels50k",
                        "dataset_hotel_id": ds,
                        "confidence": best_sc,
                        "matched_by": ["name"],
                    }
                ]
        # seed commons / iconic
        if assign_unused_urls(candidates, used_urls) is None:
            for seed_name, urls in seed_commons.items():
                if name_match_score(h["canonical_name"], seed_name) >= 0.85:
                    candidates = urls
                    source_type = "wikimedia"
                    break
        # wikidata name
        if assign_unused_urls(candidates, used_urls) is None:
            for r in pool_wd.get(h["country_code"], []):
                if name_match_score(h["canonical_name"], r["canonical_name"]) >= 0.85:
                    if assign_unused_urls(r.get("image_urls") or [], used_urls):
                        candidates = r["image_urls"]
                        source_type = "wikimedia"
                        break

        picked = take(candidates) if candidates else None
        if picked:
            h = dict(h)
            h["images"] = make_image_objs(h["id"], picked, source_type=source_type)
            if not h.get("description_ru") or len(h["description_ru"]) < 200:
                h["description_ru"] = describe_ru(h)
            if not (h.get("price") or {}).get("amount"):
                h["price"] = estimate_price(h)
            used_names.add(nn)
            if ds:
                used_ds.add(ds)
            kept.append(h)
            stats["images_reassigned"] += 1
        else:
            still.append(h)

    print(f"Pass B kept={len(kept)} still={len(still)}", flush=True)

    by_cc_kept = Counter(h["country_code"] for h in kept)
    need_by_cc = {cc: QUOTAS[cc] - by_cc_kept.get(cc, 0) for cc in QUOTAS}
    print("Shortfall", {k: v for k, v in need_by_cc.items() if v > 0}, flush=True)

    def iter_fill_candidates(cc: str) -> list[dict]:
        rows: list[dict] = []
        # iconic seeds first
        for seed in ICONIC_SEEDS:
            if seed["country_code"] != cc:
                continue
            nn = norm_name(seed["name"])
            if nn in used_names:
                continue
            commons_urls = [u for u in (seed_commons.get(seed["name"]) or []) if u]
            matched = None
            # Prefer H50K/region only when they still have unused unique images
            for r in pool_h50k.get(cc, []):
                if name_match_score(seed["name"], r["canonical_name"]) < 0.8:
                    continue
                rid = str(r["dataset_hotel_id"])
                if rid in used_ds or rid not in image_map:
                    continue
                if assign_unused_urls(image_map[rid], used_urls, min_n=MIN_IMAGES) is None:
                    continue
                matched = dict(r)
                matched["image_urls"] = image_map[rid]
                matched["official_website"] = seed.get("website")
                matched["_score"] = 80
                matched["source"] = "iconic_seed"
                break
            if not matched:
                for r in pool_region.get(cc, []):
                    if name_match_score(seed["name"], r["canonical_name"]) < 0.8:
                        continue
                    if assign_unused_urls(r.get("image_urls") or [], used_urls, min_n=MIN_IMAGES) is None:
                        continue
                    matched = dict(r)
                    matched["official_website"] = seed.get("website")
                    matched["_score"] = 80
                    matched["source"] = "iconic_seed"
                    break
            if not matched and commons_urls and assign_unused_urls(commons_urls, used_urls, min_n=MIN_IMAGES):
                matched = {
                    "canonical_name": seed["name"],
                    "official_website": seed.get("website"),
                    "country_code": cc,
                    "city": seed.get("city") or COUNTRY_META[cc]["name_ru"],
                    "resort_area": seed.get("city"),
                    "zone_key": "dubai" if str(seed.get("city") or "").lower() == "dubai" else None,
                    "image_urls": commons_urls,
                    "source": "iconic_seed",
                    "_score": 78,
                }
            if matched:
                rows.append(matched)
        rows.extend(pool_region.get(cc, []))
        rows.extend(pool_wd.get(cc, []))
        for r in pool_h50k.get(cc, []):
            rid = str(r["dataset_hotel_id"])
            if rid in image_map:
                rr = dict(r)
                rr["image_urls"] = image_map[rid]
                rows.append(rr)
        rows.sort(key=lambda x: -int(x.get("_score") or 0))
        return rows

    seq = len(kept) + 1
    replacements_log: list[str] = []
    for cc, need in need_by_cc.items():
        if need <= 0:
            continue
        cands = iter_fill_candidates(cc)
        if cc == "AE":
            dubai_now = sum(1 for h in kept if h["country_code"] == "AE" and is_dubai(h))
            dubai_need = max(0, AE_DUBAI_MIN - dubai_now)
            dubai_c = [c for c in cands if c.get("zone_key") == "dubai" or "dubai" in str(c.get("city") or "").lower() or "дубай" in str(c.get("city") or "").lower()]
            other_c = [c for c in cands if c not in dubai_c]
            cands = dubai_c + other_c
            _ = dubai_need  # preference via ordering

        for c in cands:
            if need <= 0:
                break
            nn = norm_name(c["canonical_name"])
            if not nn or nn in used_names:
                continue
            rid = str(c["dataset_hotel_id"]) if c.get("dataset_hotel_id") else None
            if rid and rid in used_ds:
                continue
            urls = c.get("image_urls") or []
            if rid and rid in image_map and not urls:
                urls = image_map[rid]
            picked = take(urls)
            if not picked:
                continue
            stype = "dataset" if rid else ("travelapi" if c.get("source") == "region" else "wikimedia")
            rec = materialize_candidate(c, seq, picked, stype)
            used_names.add(nn)
            if rid:
                used_ds.add(rid)
            kept.append(rec)
            seq += 1
            need -= 1
            stats["hotels_replaced"] += 1
            replacements_log.append(f"{cc}: +{c.get('source','h50k')} {c['canonical_name']}")
        if need > 0:
            print(f"WARNING still short {cc} by {need}", flush=True)

    # Trim to exact quotas
    final_by_cc: dict[str, list[dict]] = defaultdict(list)
    for h in kept:
        final_by_cc[h["country_code"]].append(h)

    final: list[dict] = []
    for cc, target in QUOTAS.items():
        group = final_by_cc.get(cc, [])
        group.sort(key=lambda h: (-(h.get("curation_score") or 0), h["canonical_name"]))
        if cc == "AE":
            dubai = [h for h in group if is_dubai(h)]
            other = [h for h in group if not is_dubai(h)]
            take_d = dubai[: max(AE_DUBAI_MIN, target)]
            take_o = other[: max(0, target - len(take_d))]
            if len(take_d) + len(take_o) < target:
                extra = [h for h in dubai if h not in take_d]
                take_d = take_d + extra[: target - len(take_d) - len(take_o)]
            group = (take_d + take_o)[:target]
        else:
            group = group[:target]
        final.extend(group)

    renumbered = []
    for i, h in enumerate(final, start=1):
        h = dict(h)
        new = f"oh-curated-{i:06d}"
        h["id"] = new
        for j, img in enumerate(h.get("images") or [], start=1):
            img["id"] = f"{new}-img-{j:02d}"
            img["hotel_id"] = new
        renumbered.append(h)
    final = renumbered

    rewrite_jsonl(OUT / "hotels.jsonl", final)
    rewrite_side_files(final)

    by_cc = Counter(h["country_code"] for h in final)
    dubai_count = sum(1 for h in final if h["country_code"] == "AE" and is_dubai(h))
    checks = assert_unique(final)

    progress = {
        "target": 1000,
        "completed": len(final),
        "countries": {cc: {"target": t, "completed": by_cc.get(cc, 0)} for cc, t in QUOTAS.items()},
        "last_updated": utc_now(),
        "stage": "complete",
        "dedupe_unique": {
            **stats,
            "replacements_sample": replacements_log[:50],
            "replacements_total": len(replacements_log),
            "dubai_count": dubai_count,
            "assertions": checks,
        },
        "quality": dict(Counter(h.get("data_quality") for h in final)),
    }
    (OUT / "progress.json").write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

    cache_out = {h50k_id(h): img_urls(h) for h in final if h50k_id(h)}
    (OUT / "cache" / "h50k_images_selected.json").write_text(
        json.dumps(cache_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Importing slim...", flush=True)
    import_stats = import_catalog(
        OUT / "hotels.jsonl", OUT / "catalog_db.json", ROOT / "src" / "data" / "curatedHotelsSlim.json"
    )
    print(
        json.dumps(
            {"stats": stats, "checks": checks, "by_cc": dict(by_cc), "dubai": dubai_count, "import": import_stats},
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    failures = []
    if checks["exact_dups"] or checks["name_dups"]:
        failures.append(f"name dups {checks}")
    if checks["cover_dups"] or checks["url_dups"]:
        failures.append(f"image dups {checks}")
    if checks["no_cover"]:
        failures.append(f"no_cover={checks['no_cover']}")
    if len(final) != 1000:
        failures.append(f"count={len(final)}")
    for cc, t in QUOTAS.items():
        if by_cc.get(cc, 0) != t:
            failures.append(f"quota {cc}={by_cc.get(cc)} want {t}")
    if dubai_count < AE_DUBAI_MIN:
        failures.append(f"dubai={dubai_count}")
    if failures:
        raise SystemExit("ASSERT FAILED: " + "; ".join(failures))
    print("OK: unique names, unique images, quotas satisfied", flush=True)


if __name__ == "__main__":
    main()
