"""Validate curated catalog + write reports."""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "curated_hotels"
REPORTS = ROOT / "reports"

from services.catalog.quotas import ICONIC_SEEDS, QUOTAS  # noqa: E402


def main() -> None:
    rows = [json.loads(l) for l in (OUT / "hotels.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    imgs = [
        json.loads(l)
        for l in (OUT / "image_manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    xw = [
        json.loads(l)
        for l in (OUT / "dataset_crosswalk.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    by_cc = Counter(r["country_code"] for r in rows)
    quality = Counter(r.get("data_quality") for r in rows)

    desc_ok = sum(1 for r in rows if 250 <= len(r.get("description_ru") or "") <= 500)
    prices = sum(1 for r in rows if (r.get("price") or {}).get("status") == "snapshot" and (r.get("price") or {}).get("amount"))
    website = sum(1 for r in rows if r.get("official_website"))
    coords = sum(1 for r in rows if r.get("latitude") is not None)
    imgs5 = sum(1 for r in rows if len(r.get("images") or []) >= 5)
    index_allowed = sum(1 for i in imgs if i.get("usage_status") == "index_allowed")
    dubai = sum(
        1
        for r in rows
        if r["country_code"] == "AE"
        and (r.get("zone_key") == "dubai" or str(r.get("city") or "").lower() in {"дубай", "dubai"})
    )
    unique = len({(r["country_code"], r["canonical_name"].strip().lower()) for r in rows})

    # per-country image stats
    hotel_imgs = defaultdict(list)
    for i in imgs:
        hotel_imgs[i["hotel_id"]].append(i)

    lines = []
    lines.append("# Curated Hotels Report")
    lines.append("")
    lines.append("Кураторский каталог из 1000 популярных и высоко оценённых отелей по ключевым туристическим направлениям.")
    lines.append("")
    lines.append(f"**TOTAL HOTELS:** {len(rows)}")
    lines.append("")
    lines.append("| country | target | actual |")
    lines.append("|---|---:|---:|")
    for cc, t in QUOTAS.items():
        lines.append(f"| {cc} | {t} | {by_cc.get(cc, 0)} |")
    lines.append("")
    lines.append("## Stats")
    lines.append(f"- unique hotels: {unique}")
    lines.append(f"- A quality: {quality.get('A', 0)}")
    lines.append(f"- B quality: {quality.get('B', 0)}")
    lines.append(f"- C quality: {quality.get('C', 0)}")
    lines.append(f"- official website: {website}")
    lines.append(f"- coordinates: {coords}")
    lines.append(f"- hotels with >=5 image refs: {imgs5}")
    lines.append(f"- index_allowed images: {index_allowed}")
    lines.append(f"- price snapshot/estimate: {prices}")
    lines.append(f"- Hotels50K crosswalk: {len(xw)}")
    lines.append("- OpenHotels crosswalk: 0 (dataset gated / unavailable)")
    lines.append(f"- AE Dubai count: {dubai} (min 90)")
    lines.append(f"- descriptions 250–500 chars: {desc_ok}")
    lines.append("")
    lines.append("## Visual coverage by country")
    lines.append("")
    lines.append("| cc | hotels | img refs | index_allowed | with website | with coords |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cc in QUOTAS:
        hs = [r for r in rows if r["country_code"] == cc]
        irefs = sum(len(r.get("images") or []) for r in hs)
        iallow = sum(1 for r in hs for i in (r.get("images") or []) if i.get("usage_status") == "index_allowed")
        lines.append(
            f"| {cc} | {len(hs)} | {irefs} | {iallow} | {sum(1 for r in hs if r.get('official_website'))} | {sum(1 for r in hs if r.get('latitude') is not None)} |"
        )

    # iconic check
    have = {r["canonical_name"].lower() for r in rows}
    lines.append("")
    lines.append("## Iconic sanity (§21 sample)")
    for seed in ICONIC_SEEDS[:40]:
        name = seed["name"]
        ok = any(name.lower() in h or h in name.lower() for h in have)
        lines.append(f"- {'OK' if ok else 'MISS'}: {name}")

    random.seed(42)
    samples = random.sample(rows, 20)
    lines.append("")
    lines.append("## 20 random samples")
    for s in samples:
        lines.append(
            f"- `{s['id']}` | {s['canonical_name']} | {s['country_code']} / {s['city']} | "
            f"Q={s['data_quality']} score={s['curation_score']} | "
            f"price={s['price'].get('amount')} {s['price'].get('currency')} ({s['price'].get('status')}) | "
            f"imgs={len(s.get('images') or [])}"
        )

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "CURATED_HOTELS_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    dq = []
    dq.append("# Curated Hotels Data Quality")
    dq.append("")
    dq.append("## Rules")
    dq.append("- A = official + multiple sources + images + geo")
    dq.append("- B = official or (multi-source + geo) or (Hotels-50K match + city)")
    dq.append("- C = incomplete (avoided where possible)")
    dq.append("")
    dq.append("## Summary")
    dq.append(f"- A: {quality.get('A', 0)}")
    dq.append(f"- B: {quality.get('B', 0)}")
    dq.append(f"- C: {quality.get('C', 0)}")
    dq.append("")
    dq.append("## UI fields")
    dq.append(f"- Generated RU descriptions (250–500): {desc_ok}/{len(rows)}")
    dq.append(f"- UI price snapshots (estimate, not live API): {prices}/{len(rows)}")
    dq.append("- Price metadata: `price.status=snapshot`, `source=ui_estimate`, guests=2, per=night, currency=RUB")
    dq.append("")
    dq.append("## Sources used")
    dq.append("- Hotels-50K hotel_info + train_set image URLs (index_allowed)")
    dq.append("- regionHotelsCatalog travelapi refs (reference_only)")
    dq.append("- Wikidata cache (TR) + official brand websites for iconic/seed hotels")
    dq.append("- OSM fetch skipped when network hung; seeds used for thin countries")
    dq.append("")
    dq.append("## Known gaps")
    dq.append("- OpenHotels metadata gated — no crosswalk")
    dq.append("- Review scores not scraped (no fake ratings)")
    dq.append("- Prices are UI estimates for card completeness, not booking quotes")
    c_list = [r["canonical_name"] for r in rows if r.get("data_quality") == "C"][:30]
    if c_list:
        dq.append("")
        dq.append("## Sample C-quality (needs enrichment)")
        for n in c_list:
            dq.append(f"- {n}")

    (REPORTS / "CURATED_HOTELS_DATA_QUALITY.md").write_text("\n".join(dq) + "\n", encoding="utf-8")

    stats = {
        "total": len(rows),
        "quotas_ok": all(by_cc[cc] == QUOTAS[cc] for cc in QUOTAS),
        "unique": unique,
        "quality": dict(quality),
        "descriptions": desc_ok,
        "prices": prices,
        "website": website,
        "coords": coords,
        "imgs5": imgs5,
        "index_allowed": index_allowed,
        "h50k_crosswalk": len(xw),
        "dubai": dubai,
        "samples": [
            {
                "id": s["id"],
                "name": s["canonical_name"],
                "country_code": s["country_code"],
                "city": s["city"],
                "price": s["price"].get("amount"),
            }
            for s in samples
        ],
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
