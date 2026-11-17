"""Constraint matchers for NL search over AttributeObservation values.

Returns: match | unmatch | unknown | conflict
"""
from __future__ import annotations

from typing import Any, Literal

from .models import AttributeObservation, ClaimStatus
from .registry import AttributeDefinition

MatchResult = Literal["match", "unmatch", "unknown", "conflict"]


def match_constraint(
    definition: AttributeDefinition,
    observation: AttributeObservation,
    constraint: dict[str, Any],
) -> tuple[MatchResult, str]:
    if observation.status == ClaimStatus.CONFLICTED:
        return "conflict", "observation_conflicted"
    if observation.status in {ClaimStatus.UNKNOWN, ClaimStatus.STALE}:
        return "unknown", observation.status.value

    matcher = (definition.matcher or "presence").strip()
    value = observation.value

    if matcher == "walk_max_min":
        return _walk_max_min(value, constraint)
    if matcher == "risk_max":
        return _risk_max(value, constraint)
    if matcher == "boolean_true":
        return _boolean_true(value, constraint)
    if matcher == "night_confirmed":
        return _night_confirmed(value, constraint)
    if matcher == "pharmacy_walk":
        return _pharmacy_walk(value, constraint)
    if matcher == "car_access":
        return _car_access(value, constraint)
    if matcher == "presence":
        return _presence(value, constraint)
    return "unknown", f"unknown_matcher:{matcher}"


def _walk_max_min(value: Any, c: dict[str, Any]) -> tuple[MatchResult, str]:
    if not isinstance(value, dict):
        return "unmatch", "unexpected_value_shape"
    duration_min = value.get("duration_min")
    if duration_min is None and value.get("duration_s") is not None:
        duration_min = float(value["duration_s"]) / 60.0
    max_min = c.get("max_duration_min")
    if max_min is not None:
        if duration_min is None:
            return "unmatch", "missing_duration"
        if float(duration_min) > float(max_min):
            return "unmatch", f"duration_min={duration_min} > {max_min}"
    kind = value.get("access_point_kind")
    detail = f"duration_min={duration_min}"
    if kind:
        detail += f";access_point_kind={kind}"
    return "match", detail


def _risk_max(value: Any, c: dict[str, Any]) -> tuple[MatchResult, str]:
    if not isinstance(value, dict):
        return "unmatch", "unexpected_value_shape"
    risk = value.get("risk")
    if risk == "insufficient_data":
        return "unmatch", "insufficient_data_not_quiet"
    prefer = c.get("prefer_risk") or ["low"]
    reject = set(c.get("reject_risk") or [])
    if risk in reject:
        return "unmatch", f"risk={risk}_rejected"
    if c.get("reject_nightclub") and int(
        (value.get("counts") or {}).get("amenity_nightclub") or value.get("nightclub_count_250m") or 0
    ) > 0:
        return "unmatch", "nightclub_nearby"
    if risk in prefer:
        return "match", f"risk={risk}"
    return "unmatch", f"risk={risk}_not_in_{prefer}"


def _boolean_true(value: Any, c: dict[str, Any]) -> tuple[MatchResult, str]:
    """Match boolean observations against constraint.equals (True or False).

    equals=False means the user wants the attribute absent (e.g. «без blackout»).
    """
    expected = c.get("equals", True)
    if isinstance(expected, str):
        expected = expected.strip().lower() in {"1", "true", "yes", "on"}
    expected = bool(expected)

    # Accept {has_blackout: true} / {has_courtyard: true} shapes from extractors
    if isinstance(value, dict):
        for key in ("has_blackout", "has_courtyard", "value", "equals"):
            if key in value:
                value = value.get(key)
                break

    if value is True:
        return ("match", "boolean=true") if expected else ("unmatch", "boolean=true_but_equals_false")
    if value is False:
        return ("match", "boolean=false") if not expected else ("unmatch", "boolean=false")
    return "unknown", "boolean_not_boolean"


def _night_confirmed(value: Any, c: dict[str, Any]) -> tuple[MatchResult, str]:
    """Nearby pharmacy alone is NOT a night match — need hours evidence."""
    if not isinstance(value, dict):
        return "unmatch", "unexpected_value_shape"
    if value.get("confirmed_24h") is True:
        return "match", "confirmed_24h"
    late = int(value.get("late_or_24h_count") or 0)
    if late > 0:
        return "match", f"late_or_24h_count={late}"
    # Presence of pharmacies without opening_hours ≠ night service
    if int(value.get("nearby_pharmacy_count") or 0) > 0 or int(
        value.get("pois_without_hours") or 0
    ) > 0:
        return "unmatch", "pharmacy_without_hours_not_night"
    return "unmatch", "no_late_pois"


def _pharmacy_walk(value: Any, c: dict[str, Any]) -> tuple[MatchResult, str]:
    if not isinstance(value, dict):
        return "unmatch", "unexpected_value_shape"
    if value.get("confirmed_24h") is not True and not value.get("late_or_24h"):
        return "unmatch", "night_pharmacy_not_confirmed"
    duration_min = value.get("duration_min")
    max_min = c.get("max_duration_min")
    if max_min is not None:
        if duration_min is None:
            return "unmatch", "missing_duration"
        if float(duration_min) > float(max_min):
            return "unmatch", f"duration_min={duration_min} > {max_min}"
    return "match", f"pharmacy_walk_min={duration_min}"


def _car_access(value: Any, c: dict[str, Any]) -> tuple[MatchResult, str]:
    """Parking hints are not proof of quiet street / no cars under windows."""
    if not isinstance(value, dict):
        return "unmatch", "unexpected_value_shape"
    # Window-facing traffic cannot be verified from OSM parking alone
    if c.get("require_no_street_traffic"):
        return "unknown", "street_traffic_under_windows_not_observable"
    if c.get("require_parking"):
        if value.get("parking_nearby") is True:
            return "match", "parking_nearby"
        return "unmatch", "parking_not_confirmed"
    # Pedestrian zone alone ≠ convenient car access
    if value.get("parking_nearby") is True:
        return "match", "parking_nearby"
    if value.get("pedestrian_zone_nearby") is True:
        return "unknown", "pedestrian_zone_not_car_access_proof"
    return "unmatch", "no_car_access_evidence"


def _presence(value: Any, c: dict[str, Any]) -> tuple[MatchResult, str]:
    if value is None:
        return "unknown", "no_value"
    if isinstance(value, dict):
        # family style counts
        if (
            int(value.get("playground_count") or 0)
            + int(value.get("park_count") or 0)
            > 0
        ):
            return "match", "family_pois_present"
        if any(v for v in value.values() if v not in (None, False, 0, "", [], {})):
            return "match", "object_present"
        return "unmatch", "empty_object"
    if value is False:
        return "unmatch", "false"
    return "match", "present"
