"""Shared fixtures for hotel_intelligence tests (offline, no network)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.hotel_intelligence.attributes.definitions import build_default_registry
from services.hotel_intelligence.store import IntelligenceStore

# Use a fresh reference clock so expiration-sensitive tests work after October 2026.
NOW = datetime.now(timezone.utc)

TEST_WRITE_TOKEN = "test-hi-write-token"


@pytest.fixture(autouse=True)
def _hi_security_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Writes require a server-side token; demo header alone is insufficient."""
    monkeypatch.setattr(
        "services.hotel_intelligence.config.HOTEL_INTELLIGENCE_WRITE_TOKEN",
        TEST_WRITE_TOKEN,
    )
    monkeypatch.setattr("services.hotel_intelligence.config.DEMO_MODE", True)


@pytest.fixture
def tmp_store(tmp_path: Path) -> IntelligenceStore:
    db = tmp_path / "test_intelligence.sqlite"
    store = IntelligenceStore(db_path=db)
    yield store
    store.close()


@pytest.fixture
def registry():
    return build_default_registry()


@pytest.fixture
def sample_hotel() -> dict:
    return {
        "hotel_id": "ist-demo-001",
        "name": "Demo Sultanahmet Hotel",
        "lat": 41.0055,
        "lon": 28.9769,
        "city": "Istanbul",
        "region": "istanbul",
        "sources": [
            {
                "type": "curated",
                "url": "dataset:curated:ist-demo-001",
                "checked_at": NOW.isoformat(),
            }
        ],
        "provenance": {"note": "test fixture"},
    }
