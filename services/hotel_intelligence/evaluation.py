"""Evaluation suites: technical consistency vs independent spot-checks.

Never report precision against tool-derived gold as if it were independent accuracy.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .evidence import resolve_observations
from .models import ClaimStatus
from .store import IntelligenceStore


def load_gold(path: Path | str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def evaluate_technical_consistency(
    store: IntelligenceStore,
    gold: list[dict[str, Any]] | Path | str,
) -> dict[str, Any]:
    """Check stored observations agree with technical gold fields (same pipeline).

    This is consistency / regression — NOT independent precision.
    """
    gold_rows = load_gold(gold) if isinstance(gold, (str, Path)) else list(gold)
    ok = 0
    fail = 0
    details: list[dict[str, Any]] = []
    for row in gold_rows:
        hotel_id = str(row["hotel_id"])
        attr = str(row.get("attribute_key") or "walk_to_metro")
        base_attr = attr.split(".")[0]
        obs_list = store.list_observations(hotel_id, base_attr)
        if not obs_list:
            fail += 1
            details.append({"hotel_id": hotel_id, "outcome": "missing"})
            continue
        preferred = obs_list[-1]
        kind = (preferred.value or {}).get("access_point_kind") if isinstance(preferred.value, dict) else None
        expected_kind = row.get("access_point_kind") or row.get("expected")
        status_ok = preferred.status.value == row.get("status", preferred.status.value)
        kind_ok = expected_kind is None or kind == expected_kind or (
            preferred.status == ClaimStatus.UNKNOWN and expected_kind in {"none", None}
        )
        # Line geometries must never appear as estimated entrance/station
        name = (preferred.value or {}).get("metro_name") if isinstance(preferred.value, dict) else ""
        line_leak = bool(name and ("hattı" in name.lower() or "hatti" in name.lower() or name.lower().endswith(" line")))
        if preferred.status == ClaimStatus.ESTIMATED and line_leak:
            kind_ok = False
        passed = status_ok and kind_ok and not (
            preferred.status == ClaimStatus.ESTIMATED and kind not in {"entrance", "station_node", "unconfirmed_station", None}
            and row.get("status") == "estimated"
        )
        # Stricter: estimated walk must be entrance or station_node after P0 fix
        if preferred.status == ClaimStatus.ESTIMATED and base_attr == "walk_to_metro":
            passed = kind in {"entrance", "station_node"} and not line_leak
        if passed:
            ok += 1
            details.append({"hotel_id": hotel_id, "outcome": "ok", "kind": kind})
        else:
            fail += 1
            details.append(
                {
                    "hotel_id": hotel_id,
                    "outcome": "fail",
                    "kind": kind,
                    "status": preferred.status.value,
                    "metro_name": name,
                }
            )
    return {
        "suite": "technical_consistency",
        "total": len(gold_rows),
        "ok": ok,
        "fail": fail,
        "consistency_rate": (ok / len(gold_rows)) if gold_rows else None,
        "precision": None,
        "precision_note": "Not reported — technical gold is not an independent label set.",
        "details": details,
    }


def evaluate_independent_spotcheck(
    store: IntelligenceStore,
    gold: list[dict[str, Any]] | Path | str,
) -> dict[str, Any]:
    """Small hand-reviewed spot checks. Report pass/fail counts; precision only if enough labels."""
    gold_rows = load_gold(gold) if isinstance(gold, (str, Path)) else list(gold)
    passed = 0
    failed = 0
    details: list[dict[str, Any]] = []
    for row in gold_rows:
        hotel_id = str(row["hotel_id"])
        attr = str(row["attribute_key"])
        base = attr.split(".")[0]
        field = attr.split(".")[1] if "." in attr else None
        obs_list = store.list_observations(hotel_id, base)
        ok = False
        note = ""
        if not obs_list:
            note = "missing_observation"
        else:
            o = obs_list[-1]
            val = o.value if isinstance(o.value, dict) else {}
            if field == "access_point_kind" or (
                base == "walk_to_metro" and row.get("expected_access_point_kind")
            ):
                got = val.get("access_point_kind")
                expected = row.get("expected") or row.get("expected_access_point_kind")
                ok = got == expected
                if row.get("expected_access_point_kind_not") == "line":
                    ok = got not in {None, "line", "unconfirmed_station"} or got in {
                        "entrance",
                        "station_node",
                    }
                note = f"got={got}"
            elif base == "external_noise_risk":
                risk = val.get("risk")
                forbid = set(row.get("forbid_risk") or [])
                allowed = list(row.get("expected_risk_in") or [])
                if risk in forbid:
                    ok = False
                    note = f"forbidden_risk={risk}"
                elif allowed:
                    ok = risk in allowed or (
                        risk == "insufficient_data" and "insufficient_data" in allowed
                    )
                    note = f"risk={risk}"
                elif row.get("expected_not") == "low_from_empty_bars":
                    ok = risk != "low" or bool(val.get("counts"))
                    note = f"risk={risk}"
                else:
                    ok = False
                    note = f"risk={risk}_no_rule"
            elif base == "family_infrastructure":
                expect = row.get("expected_presence")
                present = (
                    int(val.get("playground_count") or 0) + int(val.get("park_count") or 0) > 0
                )
                if expect is True:
                    ok = present and o.status.value in {"estimated", "verified", "unconfirmed"}
                elif expect is False:
                    ok = (not present) or o.status.value in {"unknown", "stale"}
                else:
                    ok = True
                note = f"present={present} status={o.status.value}"
            elif base == "car_access":
                expect = row.get("expected_parking_nearby")
                parking = bool(val.get("parking_nearby"))
                if expect is True:
                    ok = parking and o.status.value in {"estimated", "verified", "unconfirmed"}
                elif expect is False:
                    ok = (not parking) or o.status.value in {"unknown", "stale"}
                else:
                    ok = True
                note = f"parking={parking} status={o.status.value}"
            elif base == "blackout_curtains":
                # Excluded from real-fact precision; kept for methodology checks only
                ok = (
                    o.status.value == row.get("expected_status", "unconfirmed")
                    and o.scope.kind == "room_type"
                    and all(s.kind == "hotelier_simulated" for s in o.sources)
                )
                note = f"status={o.status.value} scope={o.scope.kind}"
            else:
                note = "unhandled_row"
        if ok:
            passed += 1
        else:
            failed += 1
        details.append({"hotel_id": hotel_id, "attribute_key": attr, "ok": ok, "note": note})

    n = len(gold_rows)
    return {
        "suite": "independent_spotcheck",
        "total": n,
        "passed": passed,
        "failed": failed,
        "pass_rate": (passed / n) if n else None,
        "precision": (passed / n) if n >= 30 else None,
        "precision_note": (
            None
            if n >= 30
            else f"Precision withheld — only {n} independent labels (need ≥30 for a meaningful rate)."
        ),
        "details": details,
    }


def evaluate_coverage_unknown_conflict(
    store: IntelligenceStore,
    *,
    attribute_keys: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    at = now or datetime.now(timezone.utc)
    hotels = store.list_hotels()
    keys = attribute_keys or [
        "walk_to_metro",
        "external_noise_risk",
        "night_services",
        "family_infrastructure",
        "car_access",
        "blackout_curtains",
        "late_night_pharmacy_walk",
    ]
    covered = 0
    unknown = 0
    conflicted = 0
    slots = 0
    for h in hotels:
        hid = str(h.get("hotel_id") or h.get("id"))
        for key in keys:
            slots += 1
            obs = store.list_observations(hid, key)
            if not obs:
                unknown += 1
                continue
            # Resolve each scope separately (Deluxe vs Standard must not mix)
            by_scope: dict[str, list] = {}
            for o in obs:
                sk = f"{o.scope.kind}:{o.scope.identifier or ''}"
                by_scope.setdefault(sk, []).append(o)
            scope_statuses = []
            for group in by_scope.values():
                res = resolve_observations(group, now=at)
                scope_statuses.append(res.status)
            if any(s == ClaimStatus.CONFLICTED for s in scope_statuses):
                conflicted += 1
            elif all(s in {ClaimStatus.UNKNOWN, ClaimStatus.STALE} for s in scope_statuses):
                unknown += 1
            else:
                covered += 1
    per_attr: dict[str, dict[str, int]] = {
        k: {"covered": 0, "unknown": 0, "conflicted": 0, "slots": 0} for k in keys
    }
    # Recompute per-attribute (same loop logic, tracked)
    for h in hotels:
        hid = str(h.get("hotel_id") or h.get("id"))
        for key in keys:
            per_attr[key]["slots"] += 1
            obs = store.list_observations(hid, key)
            if not obs:
                per_attr[key]["unknown"] += 1
                continue
            by_scope: dict[str, list] = {}
            for o in obs:
                sk = f"{o.scope.kind}:{o.scope.identifier or ''}"
                by_scope.setdefault(sk, []).append(o)
            scope_statuses = [resolve_observations(g, now=at).status for g in by_scope.values()]
            # insufficient_data risk counts as unknown for coverage honesty
            insuff = False
            for g in by_scope.values():
                for o in g:
                    if isinstance(o.value, dict) and o.value.get("risk") == "insufficient_data":
                        insuff = True
            if any(s == ClaimStatus.CONFLICTED for s in scope_statuses):
                per_attr[key]["conflicted"] += 1
            elif insuff or all(
                s in {ClaimStatus.UNKNOWN, ClaimStatus.STALE} for s in scope_statuses
            ):
                per_attr[key]["unknown"] += 1
            else:
                per_attr[key]["covered"] += 1

    # Align aggregate with per-attr (recompute totals honestly)
    covered = sum(v["covered"] for v in per_attr.values())
    unknown = sum(v["unknown"] for v in per_attr.values())
    conflicted = sum(v["conflicted"] for v in per_attr.values())
    return {
        "hotels": len(hotels),
        "slots": slots,
        "coverage": covered / slots if slots else 0.0,
        "unknown_rate": unknown / slots if slots else 0.0,
        "conflict_rate": conflicted / slots if slots else 0.0,
        "covered": covered,
        "unknown": unknown,
        "conflicted": conflicted,
        "per_attribute": {
            k: {
                **v,
                "coverage": v["covered"] / v["slots"] if v["slots"] else 0.0,
            }
            for k, v in per_attr.items()
        },
    }


def evaluate_latency_sample(
    store: IntelligenceStore,
    queries: list[str],
    search_fn,
) -> dict[str, Any]:
    times: list[float] = []
    for q in queries:
        t0 = time.perf_counter()
        search_fn(store, q, limit=10)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    if not times:
        return {"n": 0, "p50_ms": None, "p95_ms": None}
    def pct(p: float) -> float:
        idx = min(len(times) - 1, max(0, int(round((p / 100) * (len(times) - 1)))))
        return times[idx]
    return {
        "n": len(times),
        "p50_ms": round(pct(50), 2),
        "p95_ms": round(pct(95), 2),
        "mean_ms": round(sum(times) / len(times), 2),
    }


def full_report(
    store: IntelligenceStore,
    demo_dir: Path | str,
) -> dict[str, Any]:
    demo = Path(demo_dir)
    from .search import search_hotels

    tech = evaluate_technical_consistency(store, demo / "labeled_gold_technical.jsonl")
    indep = evaluate_independent_spotcheck(store, demo / "labeled_gold_independent.jsonl")
    cov = evaluate_coverage_unknown_conflict(store)
    lat = evaluate_latency_sample(
        store,
        [
            "тихий отель максимум 10 минут пешком от метро",
            "Deluxe с плотными шторами",
            "аптека ночью 15 минут пешком",
        ],
        search_hotels,
    )
    questions = store.list_questions()
    return {
        "technical_consistency": tech,
        "independent_spotcheck": indep,
        "coverage": cov,
        "latency": lat,
        "hotelier_question_rate": {
            "questions": len(questions),
            "hotels": len(store.list_hotels()),
            "rate": len(questions) / max(1, len(store.list_hotels())),
        },
    }
