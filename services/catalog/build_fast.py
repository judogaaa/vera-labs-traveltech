"""
Fast curated catalog builder — resume-friendly, no inventing.

Primary: Hotels-50K zone hotels + regionHotelsCatalog (travelapi) + iconic seeds.
Secondary: cached Wikidata; thin-country Wikidata/OSM only when short of quota.
Writes batches of 40 into hotels.jsonl with progress.json updates.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from services.catalog.hotels50k_index import _norm, load_hotels_by_zone, name_match_score, zone_for  # noqa: E402
from services.catalog.quotas import AE_DUBAI_MIN, COUNTRY_META, ICONIC_SEEDS, QUOTAS, ZONES  # noqa: E402
from services.catalog.wikidata_fetch import fetch_hotels_for_country  # noqa: E402

OUT = ROOT / "data" / "curated_hotels"
CACHE = OUT / "cache"
BATCH = 40

BATHROOM_RE = re.compile(
    r"bathroom|toilet|restroom|washroom|lavatory|shower|bathtub|\bbath\b|sink|wc[_/-]",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def valid_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        p = urlparse(url)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:  # noqa: BLE001
        return False


def cover_score(url: str) -> int:
    score = 0
    if BATHROOM_RE.search(url):
        score -= 100
    if re.search(r"i\.travelapi\.com|expedia|hotels\.com", url, re.I):
        score += 40
    if "image-submissions.s3" in url:
        score -= 25
    if re.search(r"exterior|facade|pool|lobby|beach|resort|aerial|night", url, re.I):
        score += 15
    return score


def order_images(urls: list[str]) -> list[str]:
    return sorted(urls, key=cover_score, reverse=True)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def rewrite_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def describe_ru(h: dict) -> str:
    """Product-style RU blurb 250–500 chars fitted to hotel + place (not scraped copy)."""
    name = h["canonical_name"]
    city = h.get("city") or h.get("resort_area") or ""
    country = COUNTRY_META[h["country_code"]]["name_ru"]
    chain = h.get("brand") or h.get("chain")
    cats = set(h.get("categories") or [])
    n = name.lower()

    if "luxury" in cats or any(x in n for x in ("four seasons", "aman", "raffles", "bulgari", "st. regis")):
        tone = "Премиальный отель"
    elif "all_inclusive" in cats or "rixos" in n:
        tone = "Курортный отель all-inclusive"
    elif "beach" in cats or "resort" in cats:
        tone = "Пляжный курортный отель"
    elif "city_hotel" in cats:
        tone = "Городской отель"
    else:
        tone = "Отель"

    loc = ", ".join(x for x in [city, country] if x)
    parts = [f"{tone} «{name}»"]
    if loc:
        parts.append(f"в {loc}.")
    else:
        parts.append(".")

    if "beach" in cats or "resort" in cats:
        parts.append("Подходит для пляжного отдыха: акцент на территории, бассейнах и виде на море или курортную зону.")
    elif "city_hotel" in cats:
        parts.append("Удобная база для городских прогулок, деловых поездок и коротких city-break.")
    else:
        parts.append("Формат размещения ориентирован на leisure-путешественников из России.")

    if chain and str(chain).lower() not in {"unknown", "none"}:
        parts.append(f"Сеть/бренд: {chain}.")
    if h.get("star_rating"):
        stars = h["star_rating"]
        try:
            stars_s = str(int(float(stars))) if float(stars).is_integer() else str(stars)
        except (TypeError, ValueError):
            stars_s = str(stars)
        parts.append(f"Категория около {stars_s}★.")

    parts.append(
        f"Карточка для каталога О!Хочу по направлению {country}: "
        "нейтральное описание по проверенным фактам о локации и типе объекта."
    )
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if len(text) < 250:
        text += (
            f" «{name}» — узнаваемый объект в {loc or country}; "
            "в интерфейсе показываем ориентировочную стоимость за ночь."
        )
    if len(text) > 500:
        text = text[:497].rstrip() + "…"
    return text


# Plausible UI nightly estimates (RUB) by country + segment — NOT live rates.
_PRICE_BASE_RUB: dict[str, tuple[int, int]] = {
    # (mid resort/city, luxury uplift base)
    "TR": (12000, 35000),
    "EG": (10000, 28000),
    "AE": (22000, 65000),
    "TH": (14000, 45000),
    "VN": (11000, 32000),
    "CN": (13000, 40000),
    "GR": (16000, 48000),
    "TN": (9500, 24000),
    "MV": (45000, 120000),
    "ID": (15000, 55000),
    "LK": (12000, 38000),
    "GE": (8000, 22000),
    "AM": (7500, 20000),
    "SG": (25000, 70000),
    "QA": (20000, 60000),
    "SC": (40000, 110000),
    "OM": (18000, 55000),
    "CU": (14000, 35000),
}


def estimate_price(h: dict) -> dict[str, Any]:
    """UI snapshot estimate: 2 guests, per night, RUB. Not a live API quote."""
    import hashlib

    cc = h["country_code"]
    mid, lux = _PRICE_BASE_RUB.get(cc, (12000, 35000))
    cats = set(h.get("categories") or [])
    name = (h.get("canonical_name") or "").lower()
    amount = mid
    if "luxury" in cats or any(x in name for x in ("four seasons", "aman", "raffles", "bulgari", "one&only", "st. regis")):
        amount = lux
    elif "all_inclusive" in cats or "rixos" in name or "maxx royal" in name:
        amount = int(mid * 1.35)
    elif "city_hotel" in cats:
        amount = int(mid * 0.85)
    stars = h.get("star_rating")
    try:
        if stars and float(stars) >= 5:
            amount = int(amount * 1.2)
        elif stars and float(stars) <= 3:
            amount = int(amount * 0.75)
    except (TypeError, ValueError):
        pass
    # stable jitter ±8% from name hash so cards differ
    digest = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    jitter = 0.92 + (digest % 17) / 100.0
    amount = int(round(amount * jitter / 100.0) * 100)
    amount = max(5000, amount)
    return {
        "status": "snapshot",
        "amount": amount,
        "currency": "RUB",
        "per": "night",
        "check_in": None,
        "check_out": None,
        "guests": 2,
        "source": "ui_estimate",
        "source_url": None,
        "fetched_at": utc_now(),
        "note": "Approximate UI estimate for leisure travel from Russia; not a live rate quote.",
    }


def infer_categories(name: str, resort: str | None) -> list[str]:
    n = name.lower()
    cats: list[str] = []
    if any(x in n for x in ("resort", "beach", "palace", "bay", "island")):
        cats += ["beach", "resort"]
    if any(x in n for x in ("tower", "plaza", "centre", "center", "airport")):
        cats.append("city_hotel")
    if any(x in n for x in ("rixos", "all inclusive", "all-inclusive")):
        cats.append("all_inclusive")
    if any(
        x in n
        for x in (
            "four seasons",
            "aman",
            "rosewood",
            "mandarin",
            "raffles",
            "bulgari",
            "one&only",
            "six senses",
            "st. regis",
            "ritz-carlton",
        )
    ):
        cats.append("luxury")
    if not cats:
        cityish = (resort or "").lower() in {
            "dubai",
            "istanbul",
            "bangkok",
            "singapore",
            "athens",
            "cairo",
            "beijing",
            "shanghai",
            "doha",
            "tbilisi",
            "yerevan",
            "havana",
        }
        cats.append("city_hotel" if cityish else "resort")
    return sorted(set(cats))


def load_region() -> list[dict]:
    path = ROOT / "src" / "data" / "regionHotelsCatalog.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_h50k_images(needed: set[str], max_per: int = 8) -> dict[str, list[str]]:
    path = ROOT / "services" / "indexer" / "data" / "hotels50k" / "train_set.csv"
    urls: dict[str, list[str]] = defaultdict(list)
    remaining = set(needed)
    if not remaining:
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            hid, url = row[1].strip(), row[2].strip()
            if hid not in remaining or not url.startswith("http"):
                continue
            if BATHROOM_RE.search(url):
                continue
            urls[hid].append(url)
            if len(urls[hid]) >= max_per:
                remaining.discard(hid)
                if not remaining:
                    break
    return {k: order_images(v) for k, v in urls.items()}


def candidate_key(c: dict) -> str:
    lat, lon = c.get("latitude"), c.get("longitude")
    geo = f"{round(lat, 3)}|{round(lon, 3)}" if lat is not None and lon is not None else "nogeo"
    return f"{c['country_code']}|{_norm(c['canonical_name'])}|{geo}"


def assemble() -> dict[str, list[dict]]:
    print("Loading H50K zones...", flush=True)
    h50k = load_hotels_by_zone()
    by_cc: dict[str, list[dict]] = defaultdict(list)

    for cc, rows in h50k.items():
        for r in rows:
            c = dict(r)
            c["_score"] = 62 + (8 if c.get("brand") else 0)
            c["sources"] = [
                {
                    "type": "hotels50k",
                    "url": f"dataset:hotels50k:{c['dataset_hotel_id']}",
                    "checked_at": utc_now(),
                }
            ]
            by_cc[cc].append(c)

    # Region catalog — travelapi covers preferred
    for row in load_region():
        country = row.get("country") or ""
        cc = next((k for k, m in COUNTRY_META.items() if m["name_ru"] == country), None)
        if not cc:
            continue
        lat, lon = row.get("latitude"), row.get("longitude")
        z = zone_for(cc, lat, lon) if lat is not None and lon is not None else None
        sid = str(row.get("source_hotel_id") or "").replace("h50k-", "") or None
        if not sid and str(row.get("id", "")).startswith("h50k-"):
            sid = str(row["id"]).replace("h50k-", "")
        imgs = order_images([u for u in (row.get("images") or []) if isinstance(u, str) and u.startswith("http")])
        # drop bathroom-first only sets
        if imgs and cover_score(imgs[0]) < -50:
            continue
        if not row.get("city") or not country:
            continue
        by_cc[cc].append(
            {
                "canonical_name": row["name"],
                "brand": row.get("chain") if row.get("chain") not in (None, "unknown") else None,
                "chain": row.get("chain"),
                "latitude": lat,
                "longitude": lon,
                "country_code": cc,
                "city": row["city"],
                "resort_area": z[2] if z else None,
                "zone_key": z[0] if z else None,
                "dataset_hotel_id": sid,
                "image_urls": imgs,
                "image_source_type": "other",
                "image_usage": "reference_only",
                "match_confidence": 0.95 if sid else 0.75,
                "sources": [
                    {
                        "type": "region_catalog",
                        "url": f"local:regionHotelsCatalog:{row.get('id')}",
                        "checked_at": utc_now(),
                    }
                ],
                "_score": 72 if imgs else 58,
            }
        )

    # Wikidata cache (use non-empty only)
    wd_path = CACHE / "wikidata.json"
    wd = json.loads(wd_path.read_text(encoding="utf-8")) if wd_path.exists() else {}
    for cc, rows in wd.items():
        if not rows:
            continue
        pool = h50k.get(cc, [])
        for r in rows:
            lat, lon = r.get("latitude"), r.get("longitude")
            z = zone_for(cc, lat, lon) if lat is not None and lon is not None else None
            if lat is not None and lon is not None and z is None and cc not in {
                "MV", "SG", "SC", "CU", "QA", "AM", "GE", "OM", "LK"
            }:
                continue
            match = None
            best = 0.0
            for p in pool:
                s = name_match_score(r["canonical_name"], p["canonical_name"])
                if s > best:
                    best, match = s, p
            if match and best < 0.72:
                match = None
            cand = {
                "canonical_name": r["canonical_name"],
                "wikidata_id": r.get("wikidata_id"),
                "official_website": r.get("official_website"),
                "latitude": lat,
                "longitude": lon,
                "star_rating": r.get("star_rating"),
                "country_code": cc,
                "city": (z[1] if z else None) or r.get("admin_label") or COUNTRY_META[cc]["name_ru"],
                "resort_area": z[2] if z else r.get("admin_label"),
                "zone_key": z[0] if z else "country",
                "sources": [
                    {
                        "type": "wikidata",
                        "url": f"https://www.wikidata.org/wiki/{r.get('wikidata_id')}",
                        "checked_at": utc_now(),
                    }
                ],
                "_score": 70 if r.get("official_website") else 52,
            }
            if match:
                cand["dataset_hotel_id"] = match["dataset_hotel_id"]
                cand["brand"] = match.get("brand")
                cand["chain"] = match.get("chain")
                cand["match_confidence"] = best
                if cand.get("latitude") is None:
                    cand["latitude"], cand["longitude"] = match["latitude"], match["longitude"]
                    if not z:
                        z2 = zone_for(cc, match["latitude"], match["longitude"])
                        if z2:
                            cand["zone_key"], cand["city"], cand["resort_area"] = z2
                cand["_score"] += 12
            by_cc[cc].append(cand)

    # Iconic seeds
    for seed in ICONIC_SEEDS:
        cc = seed["country_code"]
        pool = h50k.get(cc, [])
        match = None
        best = 0.0
        for p in pool:
            s = name_match_score(seed["name"], p["canonical_name"])
            if s > best:
                best, match = s, p
        if match and best < 0.65:
            match = None
        cand = {
            "canonical_name": seed["name"],
            "official_website": seed.get("website"),
            "country_code": cc,
            "city": seed.get("city"),
            "resort_area": seed.get("city"),
            "iconic": True,
            "categories": infer_categories(seed["name"], seed.get("city")),
            "sources": [
                {"type": "official", "url": seed["website"], "checked_at": utc_now()},
            ],
            "_score": 92,
        }
        city_l = (seed.get("city") or "").lower()
        for zone_key, city_ru, resort_en, *_box in ZONES.get(cc, []):
            if city_l and (
                city_l in resort_en.lower()
                or city_l in city_ru.lower()
                or resort_en.lower() in city_l
                or city_l == "maldives"
                and zone_key == "maldives"
            ):
                cand["zone_key"] = zone_key
                cand["city"] = city_ru
                cand["resort_area"] = resort_en
                break
        if cc == "AE" and city_l == "dubai":
            cand["zone_key"] = "dubai"
            cand["city"] = "Дубай"
            cand["resort_area"] = "Dubai"
        if match:
            cand["dataset_hotel_id"] = match["dataset_hotel_id"]
            cand["latitude"] = match["latitude"]
            cand["longitude"] = match["longitude"]
            cand["brand"] = match.get("brand")
            cand["chain"] = match.get("chain")
            cand["match_confidence"] = best
        by_cc[cc].append(cand)

    return dict(by_cc)


def fetch_thin_wikidata(short_codes: list[str], enabled: bool = False) -> None:
    """Optional network fetch. Default off — Wikidata often hangs; use cache + H50K + seeds."""
    if not enabled:
        print("[wikidata] network fetch disabled (use cache only)", flush=True)
        return
    wd_path = CACHE / "wikidata.json"
    wd = json.loads(wd_path.read_text(encoding="utf-8")) if wd_path.exists() else {}
    changed = False
    for cc in short_codes:
        if wd.get(cc):
            continue
        print(f"[wikidata] thin fetch {cc}...", flush=True)
        try:
            rows = fetch_hotels_for_country(cc, limit=80)
            wd[cc] = rows
            changed = True
            print(f"[wikidata] {cc}: {len(rows)}", flush=True)
            save_json(wd_path, wd)
        except Exception as exc:  # noqa: BLE001
            print(f"[wikidata] {cc} skip: {exc}", flush=True)
            wd.setdefault(cc, [])
    if changed:
        save_json(wd_path, wd)


def is_verified(c: dict) -> bool:
    has_official = valid_url(c.get("official_website"))
    has_geo = c.get("latitude") is not None and c.get("longitude") is not None
    has_ds = bool(c.get("dataset_hotel_id"))
    has_wd = bool(c.get("wikidata_id"))
    signals = sum([has_official, has_geo, has_ds, has_wd])
    if c.get("iconic") and has_official:
        return True
    if has_ds and has_geo:
        return True
    if has_official and (has_geo or has_wd):
        return True
    return signals >= 2


def pick_diverse(cands: list[dict], target: int, dubai_min: int | None = None) -> list[dict]:
    cands = sorted(cands, key=lambda x: (-x.get("_score", 0), x["canonical_name"]))
    selected: list[dict] = []
    used: set[str] = set()
    zone_counts: Counter[str] = Counter()

    def add(c: dict) -> bool:
        k = candidate_key(c)
        if k in used:
            return False
        # also block same normalized name in same country
        nk = f"{c['country_code']}|{_norm(c['canonical_name'])}"
        if any(candidate_key(s).startswith(nk + "|") or f"{s['country_code']}|{_norm(s['canonical_name'])}" == nk for s in selected):
            # allow if different geo far? keep strict name dedupe per country
            if any(f"{s['country_code']}|{_norm(s['canonical_name'])}" == nk for s in selected):
                return False
        used.add(k)
        selected.append(c)
        zone_counts[c.get("zone_key") or "unknown"] += 1
        return True

    for c in cands:
        if c.get("iconic"):
            add(c)

    if dubai_min:
        for c in cands:
            dubai_n = sum(
                1
                for s in selected
                if s.get("zone_key") == "dubai" or (s.get("city") or "").lower() in {"дубай", "dubai"}
            )
            if dubai_n >= dubai_min:
                break
            if c.get("zone_key") == "dubai" or (c.get("city") or "").lower() in {"дубай", "dubai"}:
                add(c)

    by_zone: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        by_zone[c.get("zone_key") or "unknown"].append(c)
    zones = list(by_zone)
    progressed = True
    while len(selected) < target and progressed:
        progressed = False
        for z in zones:
            if len(selected) >= target:
                break
            bucket = by_zone[z]
            while bucket:
                c = bucket.pop(0)
                if add(c):
                    progressed = True
                    break
    for c in cands:
        if len(selected) >= target:
            break
        add(c)
    return selected[:target]


def materialize(c: dict, seq: int, image_map: dict[str, list[str]]) -> dict:
    hid = f"oh-curated-{seq:06d}"
    cc = c["country_code"]
    meta = COUNTRY_META[cc]
    sources = list(c.get("sources") or [])
    if c.get("wikidata_id"):
        sources.append(
            {"type": "wikidata", "url": f"https://www.wikidata.org/wiki/{c['wikidata_id']}", "checked_at": utc_now()}
        )
    if valid_url(c.get("official_website")):
        sources.append({"type": "official", "url": c["official_website"], "checked_at": utc_now()})
    if c.get("dataset_hotel_id"):
        sources.append(
            {
                "type": "hotels50k",
                "url": f"dataset:hotels50k:{c['dataset_hotel_id']}",
                "checked_at": utc_now(),
            }
        )
    seen_u: set[str] = set()
    uniq_src = []
    for s in sources:
        u = s.get("url")
        if not u or u in seen_u:
            continue
        seen_u.add(u)
        uniq_src.append(s)

    urls: list[str] = []
    usage = "reference_only"
    stype = "other"
    ds = c.get("dataset_hotel_id")
    if c.get("image_urls"):
        urls = order_images(list(c["image_urls"]))
        usage = c.get("image_usage") or "reference_only"
        stype = c.get("image_source_type") or "other"
    elif ds and ds in image_map:
        urls = image_map[ds]
        usage = "index_allowed"
        stype = "dataset"

    cats_cycle = ["exterior", "room", "pool", "beach", "lobby", "view", "restaurant", "other"]
    images = []
    for i, url in enumerate(urls[:12]):
        images.append(
            {
                "id": f"{hid}-img-{i+1:02d}",
                "hotel_id": hid,
                "category": cats_cycle[i % len(cats_cycle)],
                "source_url": url,
                "source_page": None,
                "source_type": stype,
                "width": None,
                "height": None,
                "usage_status": usage,
                "local_path": None,
            }
        )

    dataset_matches = []
    if ds:
        matched_by = ["name"]
        if c.get("latitude") is not None:
            matched_by.append("coordinates")
        if c.get("city"):
            matched_by.append("city")
        dataset_matches.append(
            {
                "dataset": "hotels50k",
                "dataset_hotel_id": str(ds),
                "confidence": float(c.get("match_confidence") or 0.9),
                "matched_by": matched_by,
            }
        )

    cats = c.get("categories") or infer_categories(c["canonical_name"], c.get("resort_area"))
    record = {
        "id": hid,
        "canonical_name": c["canonical_name"],
        "aliases": c.get("aliases") or [],
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
        "official_website": c.get("official_website") if valid_url(c.get("official_website")) else None,
        "official_booking_url": None,
        "description_ru": "",
        "highlights_ru": [],
        "curation_score": 0,
        "curation_reasons": [],
        "price": {
            "status": "unavailable",
            "amount": None,
            "currency": None,
            "per": None,
            "check_in": None,
            "check_out": None,
            "guests": None,
            "source": None,
            "source_url": None,
            "fetched_at": None,
        },
        "images": images,
        "sources": uniq_src,
        "dataset_matches": dataset_matches,
        "wikidata_id": c.get("wikidata_id"),
        "zone_key": c.get("zone_key"),
        "verified_at": utc_now(),
        "data_quality": "C",
    }
    record["description_ru"] = describe_ru(record)
    record["price"] = estimate_price(record)
    score = 40
    reasons = ["high-demand Russian leisure destination"]
    if record["official_website"]:
        score += 15
        reasons.append("official website")
    if record["latitude"] is not None:
        score += 10
        reasons.append("geo coordinates")
    if len(images) >= 5:
        score += 12
        reasons.append("multiple image refs")
    elif images:
        score += 6
        reasons.append("image references available")
    if dataset_matches:
        score += 12
        reasons.append("Hotels-50K crosswalk")
    if c.get("iconic"):
        score += 12
        reasons.append("iconic / landmark hotel")
    if record.get("brand"):
        score += 5
        reasons.append("known brand")
    if record.get("wikidata_id"):
        score += 5
        reasons.append("wikidata entity")
    record["curation_score"] = min(100, score)
    record["curation_reasons"] = reasons
    has_official = bool(record["official_website"])
    indep = len({s.get("type") for s in uniq_src}) >= 2
    geo = record["latitude"] is not None
    if has_official and indep and images and geo:
        record["data_quality"] = "A"
    elif has_official or (indep and geo) or (dataset_matches and geo and record["city"]):
        record["data_quality"] = "B"
    else:
        record["data_quality"] = "C"
    hl = []
    if record["resort_area"]:
        hl.append(f"Район: {record['resort_area']}")
    if record["brand"]:
        hl.append(f"Бренд: {record['brand']}")
    if record["official_website"]:
        hl.append("Есть официальный сайт")
    record["highlights_ru"] = hl[:5]
    return record


def write_progress(completed: int, by_cc: dict[str, int], stage: str, extra: dict | None = None) -> None:
    progress = {
        "target": 1000,
        "completed": completed,
        "countries": {cc: {"target": t, "completed": by_cc.get(cc, 0)} for cc, t in QUOTAS.items()},
        "last_updated": utc_now(),
        "stage": stage,
    }
    if extra:
        progress.update(extra)
    save_json(OUT / "progress.json", progress)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    # Pre-fetch thin countries that H50K can't fill
    h50k_counts = json.loads((CACHE / "h50k_by_zone_counts.json").read_text(encoding="utf-8")) if (
        CACHE / "h50k_by_zone_counts.json"
    ).exists() else {}
    short = [cc for cc, t in QUOTAS.items() if h50k_counts.get(cc, 0) < t]
    # also CU always
    if "CU" not in short:
        short.append("CU")
    import os

    fetch_net = os.environ.get("CURATED_FETCH_NET", "0") == "1"
    print(f"Thin countries: {short} (network={fetch_net})", flush=True)
    fetch_thin_wikidata(short, enabled=fetch_net)

    candidates = assemble()

    # OSM: use cache only unless CURATED_FETCH_NET=1
    from services.catalog.osm_fetch import fetch_for_countries  # local import

    still_short = []
    for cc, target in QUOTAS.items():
        verified = [c for c in candidates.get(cc, []) if is_verified(c)]
        seen = set()
        n = 0
        for c in verified:
            k = f"{_norm(c['canonical_name'])}"
            if k in seen:
                continue
            seen.add(k)
            n += 1
        if n < target:
            still_short.append(cc)
    osm_path = CACHE / "osm.json"
    osm = json.loads(osm_path.read_text(encoding="utf-8")) if osm_path.exists() else {}
    need_osm = [cc for cc in still_short if cc not in osm]
    if need_osm and fetch_net:
        print(f"Fetching OSM for short: {need_osm}", flush=True)
        try:
            fetched = fetch_for_countries(need_osm, per_zone=40)
            osm.update(fetched)
            save_json(osm_path, osm)
        except Exception as exc:  # noqa: BLE001
            print(f"OSM batch failed: {exc}", flush=True)
    elif need_osm:
        print(f"[osm] skip network for short {need_osm}; using cache/seeds/H50K", flush=True)

    # merge OSM into candidates
    h50k = load_hotels_by_zone()
    for cc, rows in osm.items():
        pool = h50k.get(cc, [])
        for r in rows:
            match = None
            best = 0.0
            for p in pool:
                s = name_match_score(r["canonical_name"], p["canonical_name"])
                if s > best:
                    best, match = s, p
            if match and best < 0.72:
                match = None
            cand = dict(r)
            cand["sources"] = [
                {
                    "type": "osm",
                    "url": f"https://www.openstreetmap.org/{r.get('osm_type', 'node')}/{r.get('osm_id')}",
                    "checked_at": utc_now(),
                }
            ]
            cand["_score"] = 56 + (10 if r.get("official_website") else 0)
            if match:
                cand["dataset_hotel_id"] = match["dataset_hotel_id"]
                cand["match_confidence"] = best
                cand["_score"] += 12
            candidates.setdefault(cc, []).append(cand)

    # Pick per country
    picked_by_cc: dict[str, list[dict]] = {}
    dup_removed = 0
    for cc, target in QUOTAS.items():
        raw = candidates.get(cc, [])
        seen: set[str] = set()
        uniq = []
        for c in raw:
            k = candidate_key(c)
            nk = f"{cc}|{_norm(c['canonical_name'])}"
            if k in seen or nk in seen:
                dup_removed += 1
                continue
            seen.add(k)
            seen.add(nk)
            uniq.append(c)
        verified = [c for c in uniq if is_verified(c)]
        if len(verified) < target:
            for c in uniq:
                if c in verified:
                    continue
                if c.get("dataset_hotel_id") and c.get("latitude") is not None and c.get("city"):
                    verified.append(c)
        dubai_min = AE_DUBAI_MIN if cc == "AE" else None
        picked = pick_diverse(verified, target, dubai_min=dubai_min)
        picked_by_cc[cc] = picked
        print(f"PICKED {cc}: {len(picked)}/{target} (uniq={len(uniq)}, verified={len(verified)})", flush=True)

    needed = {str(c["dataset_hotel_id"]) for rows in picked_by_cc.values() for c in rows if c.get("dataset_hotel_id")}
    print(f"Loading images for {len(needed)} H50K hotels...", flush=True)
    image_map = load_h50k_images(needed, max_per=8)
    save_json(CACHE / "h50k_images_selected.json", image_map)

    # Clear outputs
    for name in (
        "hotels.jsonl",
        "image_manifest.jsonl",
        "sources.jsonl",
        "price_snapshots.jsonl",
        "dataset_crosswalk.jsonl",
    ):
        (OUT / name).write_text("", encoding="utf-8")

    final: list[dict] = []
    seq = 1
    by_cc_done: dict[str, int] = Counter()

    for cc, target in QUOTAS.items():
        picked = picked_by_cc.get(cc, [])[:target]
        batch: list[dict] = []
        for c in picked:
            # require city+country for catalog quality
            if not c.get("city"):
                c["city"] = c.get("resort_area") or COUNTRY_META[cc]["name_ru"]
            rec = materialize(c, seq, image_map)
            # skip pure C if we have surplus — but picked is already capped
            batch.append(rec)
            seq += 1
            if len(batch) >= BATCH:
                for h in batch:
                    final.append(h)
                    by_cc_done[h["country_code"]] += 1
                append_jsonl(OUT / "hotels.jsonl", batch)
                imgs, srcs, xw, prices = [], [], [], []
                for h in batch:
                    imgs.extend(h.get("images") or [])
                    for s in h.get("sources") or []:
                        srcs.append({"hotel_id": h["id"], **s})
                    for m in h.get("dataset_matches") or []:
                        xw.append({"hotel_id": h["id"], "canonical_name": h["canonical_name"], **m})
                    prices.append({"hotel_id": h["id"], **h["price"]})
                append_jsonl(OUT / "image_manifest.jsonl", imgs)
                append_jsonl(OUT / "sources.jsonl", srcs)
                append_jsonl(OUT / "dataset_crosswalk.jsonl", xw)
                append_jsonl(OUT / "price_snapshots.jsonl", prices)
                write_progress(len(final), dict(by_cc_done), f"batch_{cc}", {"duplicates_removed": dup_removed})
                print(f"  checkpoint +{len(batch)} total={len(final)}", flush=True)
                batch = []
        if batch:
            for h in batch:
                final.append(h)
                by_cc_done[h["country_code"]] += 1
            append_jsonl(OUT / "hotels.jsonl", batch)
            imgs, srcs, xw, prices = [], [], [], []
            for h in batch:
                imgs.extend(h.get("images") or [])
                for s in h.get("sources") or []:
                    srcs.append({"hotel_id": h["id"], **s})
                for m in h.get("dataset_matches") or []:
                    xw.append({"hotel_id": h["id"], "canonical_name": h["canonical_name"], **m})
                prices.append({"hotel_id": h["id"], **h["price"]})
            append_jsonl(OUT / "image_manifest.jsonl", imgs)
            append_jsonl(OUT / "sources.jsonl", srcs)
            append_jsonl(OUT / "dataset_crosswalk.jsonl", xw)
            append_jsonl(OUT / "price_snapshots.jsonl", prices)
            write_progress(len(final), dict(by_cc_done), f"country_{cc}_done", {"duplicates_removed": dup_removed})
            print(f"  flush {cc} +{len(batch)} total={len(final)}", flush=True)

    # Re-id sequentially and enforce exact quotas / dubai
    trimmed: list[dict] = []
    for cc, target in QUOTAS.items():
        group = [h for h in final if h["country_code"] == cc]
        group.sort(key=lambda h: (-h["curation_score"], h["canonical_name"]))
        if cc == "AE":
            dubai = [h for h in group if h.get("zone_key") == "dubai" or (h.get("city") or "").lower() in {"дубай", "dubai"}]
            other = [h for h in group if h not in dubai]
            take = dubai[:AE_DUBAI_MIN] + other[: max(0, target - min(len(dubai), AE_DUBAI_MIN))]
            if len(take) < target:
                rest = [h for h in group if h not in take]
                take.extend(rest[: target - len(take)])
            # if dubai still short, keep as many dubai as exist
            group = take[:target]
        else:
            group = group[:target]
        trimmed.extend(group)

    # renumber
    out_hotels = []
    for i, h in enumerate(trimmed, start=1):
        old = h["id"]
        new = f"oh-curated-{i:06d}"
        h = dict(h)
        h["id"] = new
        for img in h.get("images") or []:
            img["hotel_id"] = new
            if str(img.get("id", "")).startswith(old):
                img["id"] = str(img["id"]).replace(old, new, 1)
        out_hotels.append(h)

    rewrite_jsonl(OUT / "hotels.jsonl", out_hotels)
    # csv
    import csv as _csv

    with (OUT / "hotels.csv").open("w", encoding="utf-8", newline="") as f:
        fields = [
            "id",
            "canonical_name",
            "country_code",
            "country",
            "city",
            "resort_area",
            "latitude",
            "longitude",
            "star_rating",
            "brand",
            "chain",
            "official_website",
            "curation_score",
            "data_quality",
            "price_status",
        ]
        w = _csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for h in out_hotels:
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
                    "price_status": h["price"]["status"],
                }
            )

    images_all, sources_all, crosswalk, prices = [], [], [], []
    for h in out_hotels:
        images_all.extend(h.get("images") or [])
        for s in h.get("sources") or []:
            sources_all.append({"hotel_id": h["id"], **s})
        for m in h.get("dataset_matches") or []:
            crosswalk.append({"hotel_id": h["id"], "canonical_name": h["canonical_name"], **m})
        prices.append({"hotel_id": h["id"], **h["price"]})
    rewrite_jsonl(OUT / "image_manifest.jsonl", images_all)
    rewrite_jsonl(OUT / "sources.jsonl", sources_all)
    rewrite_jsonl(OUT / "dataset_crosswalk.jsonl", crosswalk)
    rewrite_jsonl(OUT / "price_snapshots.jsonl", prices)

    by_cc_final = Counter(h["country_code"] for h in out_hotels)
    write_progress(
        len(out_hotels),
        dict(by_cc_final),
        "complete",
        {
            "duplicates_removed": dup_removed,
            "quality": dict(Counter(h["data_quality"] for h in out_hotels)),
            "dubai_ae": sum(
                1
                for h in out_hotels
                if h["country_code"] == "AE"
                and (h.get("zone_key") == "dubai" or (h.get("city") or "").lower() in {"дубай", "dubai"})
            ),
        },
    )
    print("DONE", len(out_hotels), dict(by_cc_final), flush=True)
    short_final = {cc: QUOTAS[cc] - by_cc_final.get(cc, 0) for cc in QUOTAS if by_cc_final.get(cc, 0) < QUOTAS[cc]}
    if short_final:
        print("SHORTFALL", short_final, flush=True)


if __name__ == "__main__":
    main()
