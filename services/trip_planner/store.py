from __future__ import annotations

import json
from pathlib import Path

from . import config
from .models import Trip


class TripStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or config.TRIP_STORE_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, trip_id: str) -> Path:
        safe = "".join(c for c in trip_id if c.isalnum() or c in "-_")
        return self.root / f"{safe}.json"

    def save(self, trip: Trip) -> Trip:
        path = self._path(trip.id)
        path.write_text(trip.model_dump_json(indent=2), encoding="utf-8")
        return trip

    def get(self, trip_id: str) -> Trip | None:
        path = self._path(trip_id)
        if not path.exists():
            return None
        return Trip.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, trip_id: str) -> bool:
        path = self._path(trip_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))
