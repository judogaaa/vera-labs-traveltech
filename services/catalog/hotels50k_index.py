"""Load Hotels-50K metadata and assign resort zones for target countries."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .quotas import ZONES

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "services" / "indexer" / "data" / "hotels50k"


def _norm(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    for tok in (
        "hotel",
        "resort",
        "spa",
        "all inclusive",
        "all-inclusive",
        "the",
        "and",
        "by",
        "luxury",
        "collection",
    ):
        s = re.sub(rf"\b{re.escape(tok)}\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_chains() -> dict[str, str]:
    chains: dict[str, str] = {}
    with (META / "chain_info.csv").open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) >= 2:
                chains[row[0].strip()] = row[1].strip()
    return chains


def load_image_urls(max_per_hotel: int = 12) -> dict[str, list[str]]:
    """Scan train_set.csv for image URLs keyed by hotel_id (may be large)."""
    path = META / "train_set.csv"
    if not path.exists():
        return {}
    urls: dict[str, list[str]] = defaultdict(list)
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        # Expected: hotel_id, image_id, url or similar — detect columns
        if not header:
            return {}
        header_l = [h.strip().lower() for h in header]
        # Hotels-50K train_set often: chain_id,hotel_id,timestamp,img_path,url? — inspect flexibly
        try:
            hid_idx = header_l.index("hotel_id")
        except ValueError:
            hid_idx = 1 if len(header_l) > 1 else 0
        url_idx = None
        for cand in ("url", "image_url", "img_url"):
            if cand in header_l:
                url_idx = header_l.index(cand)
                break
        if url_idx is None:
            # fallback: last column if looks like url
            url_idx = len(header_l) - 1
        for row in reader:
            if len(row) <= max(hid_idx, url_idx):
                continue
            hid = row[hid_idx].strip()
            url = row[url_idx].strip()
            if not hid or not url.startswith("http"):
                continue
            if len(urls[hid]) >= max_per_hotel:
                continue
            urls[hid].append(url)
    return dict(urls)


def zone_for(country_code: str, lat: float, lon: float) -> tuple[str, str, str] | None:
    for zone_key, city_ru, resort_en, a, b, c, d in ZONES.get(country_code, []):
        if a <= lat <= b and c <= lon <= d:
            return zone_key, city_ru, resort_en
    return None


def load_hotels_by_zone() -> dict[str, list[dict[str, Any]]]:
    chains = load_chains()
    by_cc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with (META / "hotel_info.csv").open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 5:
                continue
            hid = row[0].strip()
            name = row[1].strip()
            chain_id = row[2].strip()
            try:
                lat = float(row[3]) if row[3].strip() else None
                lon = float(row[4]) if row[4].strip() else None
            except ValueError:
                lat = lon = None
            if lat is None or lon is None:
                continue
            for cc in ZONES:
                z = zone_for(cc, lat, lon)
                if not z:
                    continue
                zone_key, city_ru, resort_en = z
                by_cc[cc].append(
                    {
                        "dataset": "hotels50k",
                        "dataset_hotel_id": hid,
                        "canonical_name": name,
                        "brand": chains.get(chain_id) if chains.get(chain_id, "").lower() != "unknown" else None,
                        "chain": chains.get(chain_id),
                        "latitude": lat,
                        "longitude": lon,
                        "country_code": cc,
                        "city": city_ru,
                        "resort_area": resort_en,
                        "zone_key": zone_key,
                        "norm_name": _norm(name),
                        "source": "hotels50k",
                    }
                )
                break
    return dict(by_cc)


def name_match_score(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.85
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return 0.0
    j = len(ta & tb) / len(ta | tb)
    return j
