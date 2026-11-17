"""Resolve Hotels-50K / OpenHotels dataset IDs to curated hotel records."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "curated_hotels" / "catalog_db.json"


def _norm(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


class HotelResolver:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB
        self._db: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._db is None:
            if not self.db_path.exists():
                raise FileNotFoundError(
                    f"Catalog DB missing at {self.db_path}. Run: python -m services.catalog.import_curated_hotels"
                )
            self._db = json.loads(self.db_path.read_text(encoding="utf-8"))
        return self._db

    def get_by_id(self, hotel_id: str) -> dict[str, Any] | None:
        db = self.load()
        hotels = db["hotels"]
        idx = db.get("by_id", {}).get(hotel_id)
        if idx is None:
            for h in hotels:
                if h["id"] == hotel_id:
                    return h
            return None
        return hotels[idx]

    def resolve_dataset(self, dataset: str, dataset_hotel_id: str) -> dict[str, Any] | None:
        db = self.load()
        key = f"{dataset}:{dataset_hotel_id}"
        matches = db.get("crosswalk", {}).get(key) or []
        if not matches:
            # also try without prefix variants
            alt = f"{dataset}:{dataset_hotel_id.lstrip('0')}" if dataset_hotel_id.isdigit() else None
            if alt:
                matches = db.get("crosswalk", {}).get(alt) or []
        if not matches:
            return None
        best = max(matches, key=lambda m: float(m.get("confidence") or 0))
        hotel = self.get_by_id(best["hotel_id"])
        if not hotel:
            return None
        return {
            "curated": hotel,
            "match": best,
            "card": self.to_rich_card(hotel),
        }

    def resolve_hotels50k(self, hotel_id: str) -> dict[str, Any] | None:
        hid = hotel_id.replace("h50k-", "")
        return self.resolve_dataset("hotels50k", hid)

    def search(self, q: str, limit: int = 20) -> list[dict[str, Any]]:
        db = self.load()
        ql = q.strip().lower()
        if not ql:
            return []
        scored: list[tuple[int, dict[str, Any]]] = []
        for h in db["hotels"]:
            hay = " ".join(
                [
                    h.get("canonical_name") or "",
                    " ".join(h.get("aliases") or []),
                    h.get("brand") or "",
                    h.get("chain") or "",
                    h.get("city") or "",
                    h.get("resort_area") or "",
                    h.get("country") or "",
                    h.get("country_code") or "",
                ]
            ).lower()
            if ql not in hay and _norm(ql) not in _norm(hay):
                continue
            score = h.get("curation_score") or 0
            if (h.get("canonical_name") or "").lower().startswith(ql):
                score += 20
            scored.append((score, h))
        scored.sort(key=lambda x: (-x[0], x[1]["canonical_name"]))
        return [h for _, h in scored[:limit]]

    def to_rich_card(self, hotel: dict[str, Any]) -> dict[str, Any]:
        images = [
            img["source_url"]
            for img in (hotel.get("images") or [])
            if img.get("source_url")
        ]
        return {
            "id": hotel["id"],
            "name": hotel["canonical_name"],
            "city": hotel.get("city"),
            "country": hotel.get("country"),
            "description": hotel.get("description_ru"),
            "images": images[:12],
            "price_status": (hotel.get("price") or {}).get("status", "unavailable"),
            "amenities": hotel.get("amenities") or hotel.get("categories") or [],
            "official_website": hotel.get("official_website"),
            "curation_score": hotel.get("curation_score"),
            "data_quality": hotel.get("data_quality"),
        }
