"""Catalog search FastAPI router.

Mounted from search_api.main:
  GET /api/catalog/hotels?q=
  GET /api/catalog/hotels/{id}
  GET /api/catalog/countries
  GET /api/catalog/destinations
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .hotel_resolver import HotelResolver
from .quotas import COUNTRY_META, QUOTAS

router = APIRouter(prefix="/api/catalog", tags=["catalog"])
_resolver = HotelResolver()


def _public_hotel(h: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": h["id"],
        "canonical_name": h.get("canonical_name"),
        "brand": h.get("brand"),
        "chain": h.get("chain"),
        "country": h.get("country"),
        "country_code": h.get("country_code"),
        "city": h.get("city"),
        "resort_area": h.get("resort_area"),
        "latitude": h.get("latitude"),
        "longitude": h.get("longitude"),
        "star_rating": h.get("star_rating"),
        "categories": h.get("categories") or [],
        "amenities": h.get("amenities") or [],
        "description_ru": h.get("description_ru"),
        "highlights_ru": h.get("highlights_ru") or [],
        "official_website": h.get("official_website"),
        "curation_score": h.get("curation_score"),
        "data_quality": h.get("data_quality"),
        "price": h.get("price"),
        "images": [
            {
                "id": img.get("id"),
                "category": img.get("category"),
                "source_url": img.get("source_url"),
                "usage_status": img.get("usage_status"),
            }
            for img in (h.get("images") or [])[:16]
        ],
        "aliases": h.get("aliases") or [],
    }


@router.get("/hotels")
def list_hotels(
    q: str = Query("", description="Search by name, alias, brand, city, country"),
    country: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    try:
        db = _resolver.load()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    hotels = db["hotels"]
    if q.strip():
        hotels = _resolver.search(q, limit=1000)
    if country:
        cc = country.upper()
        hotels = [
            h
            for h in hotels
            if h.get("country_code") == cc or (h.get("country") or "").lower() == country.lower()
        ]
    total = len(hotels)
    page = hotels[offset : offset + limit]
    return {"total": total, "offset": offset, "limit": limit, "hotels": [_public_hotel(h) for h in page]}


@router.get("/hotels/{hotel_id}")
def get_hotel(hotel_id: str) -> dict[str, Any]:
    try:
        hotel = _resolver.get_by_id(hotel_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not hotel:
        raise HTTPException(status_code=404, detail="Hotel not found")
    return _public_hotel(hotel)


@router.get("/countries")
def list_countries() -> dict[str, Any]:
    try:
        db = _resolver.load()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    counts = Counter(h.get("country_code") for h in db["hotels"])
    countries = []
    for cc, target in QUOTAS.items():
        meta = COUNTRY_META[cc]
        countries.append(
            {
                "country_code": cc,
                "name_en": meta["name_en"],
                "name_ru": meta["name_ru"],
                "target": target,
                "count": counts.get(cc, 0),
            }
        )
    return {"countries": countries}


@router.get("/destinations")
def list_destinations() -> dict[str, Any]:
    try:
        db = _resolver.load()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    dest: dict[tuple[str, str], int] = Counter()
    for h in db["hotels"]:
        key = (h.get("country_code") or "", h.get("resort_area") or h.get("city") or "")
        if key[0] and key[1]:
            dest[key] += 1
    destinations = [
        {
            "country_code": cc,
            "country": COUNTRY_META.get(cc, {}).get("name_ru", cc),
            "name": name,
            "hotel_count": count,
        }
        for (cc, name), count in sorted(dest.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))
    ]
    return {"destinations": destinations}


@router.get("/resolve")
def resolve_dataset(
    dataset: str = Query("hotels50k"),
    dataset_hotel_id: str = Query(...),
) -> dict[str, Any]:
    try:
        result = _resolver.resolve_dataset(dataset, dataset_hotel_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="No curated match")
    return {
        "match": result["match"],
        "hotel": _public_hotel(result["curated"]),
        "card": result["card"],
    }
