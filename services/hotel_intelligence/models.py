"""Strict contracts for evidence-backed hotel attributes.

A value must carry provenance, timestamps, scope, a method and confidence.
"Verified" means a checked supporting source/calculation, not guaranteed truth.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    ESTIMATED = "estimated"
    UNCONFIRMED = "unconfirmed"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"
    STALE = "stale"


class AttributeScope(BaseModel):
    kind: Literal["hotel", "building", "facade", "room_type", "room"]
    identifier: str | None = None

    @model_validator(mode="after")
    def require_identifier_for_specific_scope(self) -> "AttributeScope":
        if self.kind in {"facade", "room_type", "room"} and not self.identifier:
            raise ValueError("Specific facade or room scope needs a stable identifier")
        return self


class EvidenceSource(BaseModel):
    kind: Literal[
        "osm", "osrm", "wikidata", "official_site", "public_dataset",
        "hotelier", "hotelier_simulated", "calculation",
    ]
    uri: str = Field(min_length=1)
    fetched_at: datetime
    published_at: datetime | None = None

    @model_validator(mode="after")
    def require_timezone(self) -> "EvidenceSource":
        for dt in (self.fetched_at, self.published_at):
            if dt is not None and (dt.tzinfo is None or dt.utcoffset() is None):
                raise ValueError("All evidence dates must include timezone")
        return self


class AttributeObservation(BaseModel):
    observation_id: str = Field(min_length=1)
    hotel_id: str = Field(min_length=1)
    attribute_key: str = Field(min_length=1)
    scope: AttributeScope
    value: Any = None
    unit: str | None = None
    status: ClaimStatus
    sources: list[EvidenceSource] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_at: datetime
    valid_until: datetime | None = None
    method: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    calculation_inputs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provenance(self) -> "AttributeObservation":
        dates = [self.observed_at, self.valid_until]
        if any(dt is not None and (dt.tzinfo is None or dt.utcoffset() is None) for dt in dates):
            raise ValueError("Observation dates must have explicit timezone")
        if self.valid_until is not None and self.valid_until <= self.observed_at:
            raise ValueError("valid_until must be later than observed_at")
        if self.status == ClaimStatus.UNKNOWN:
            if self.value is not None:
                raise ValueError("Unknown cannot contain a fabricated value")
        elif self.status in {ClaimStatus.VERIFIED, ClaimStatus.ESTIMATED, ClaimStatus.UNCONFIRMED}:
            if self.value is None:
                raise ValueError("A stated attribute needs a value")
            if not self.sources:
                raise ValueError("A stated attribute must have source evidence")
            if self.confidence is None:
                raise ValueError("A stated attribute must have a confidence estimate")
            if self.status == ClaimStatus.VERIFIED and all(
                src.kind == "hotelier_simulated" for src in self.sources
            ):
                raise ValueError("A simulated hotelier cannot alone verify a real-world claim")
        return self

    def is_expired(self, now: datetime) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return self.valid_until is not None and now >= self.valid_until
