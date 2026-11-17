"""Ostrovok Hotel Intelligence: evidence-backed hotel attributes addon.

Contracts (models / evidence / registry) are stable. Store, providers,
calculators, agents, orchestrator, search and API extend the addon without
touching visual-search, trip-planner core, Qdrant or ML.
"""

from .models import AttributeObservation, AttributeScope, ClaimStatus, EvidenceSource
from .registry import AttributeDefinition, AttributeRegistry

__all__ = [
    "AttributeObservation",
    "AttributeScope",
    "ClaimStatus",
    "EvidenceSource",
    "AttributeDefinition",
    "AttributeRegistry",
]
