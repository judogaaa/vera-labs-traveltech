"""Deterministic parse quality for multi-condition queries (no live GigaChat)."""
from __future__ import annotations

from services.hotel_intelligence.search import parse_query_structured


def _keys(parsed) -> set[str]:
    return {r.key for r in parsed.requested}


def _req(parsed, key: str):
    for r in parsed.requested:
        if r.key == key:
            return r
    return None


def test_q01_quiet_and_metro() -> None:
    p = parse_query_structured(
        "Тихий отель в Стамбуле рядом с метро", prefer_gigachat=False
    )
    assert "external_noise_risk" in _keys(p)
    assert "walk_to_metro" in _keys(p)
    assert p.city
    assert "стамбул" in p.city.lower() or "istanbul" in (p.city or "").lower()


def test_q03_standard_without_blackout_equals_false() -> None:
    p = parse_query_structured("Standard без blackout", prefer_gigachat=False)
    b = _req(p, "blackout_curtains")
    assert b is not None
    assert b.constraint.get("equals") is False
    assert (b.constraint.get("room_type") or "").lower() == "standard"


def test_q11_family_room_courtyard_not_family_infra() -> None:
    p = parse_query_structured("Семейный номер, тихий двор", prefer_gigachat=False)
    assert p.room_type == "Family"
    assert "courtyard_rooms" in _keys(p)
    assert "family_infrastructure" not in _keys(p)
    assert "external_noise_risk" in _keys(p)


def test_q13_contradiction_recorded() -> None:
    p = parse_query_structured(
        "Хочу и тишину и рядом клубную улицу", prefer_gigachat=False
    )
    assert "external_noise_risk" in _keys(p)
    assert any(
        (u.get("attribute_key") or "").startswith("contradiction")
        for u in (p.unsupported or [])
    )


def test_no_duplicate_keys() -> None:
    p = parse_query_structured(
        "Тихий отель рядом с метро и метро до 10 минут", prefer_gigachat=False
    )
    keys = [r.key for r in p.requested]
    assert len(keys) == len(set(keys))


def test_blackout_positive_still_equals_true() -> None:
    p = parse_query_structured("Deluxe с плотными шторами blackout", prefer_gigachat=False)
    b = _req(p, "blackout_curtains")
    assert b is not None
    assert b.constraint.get("equals") is True
