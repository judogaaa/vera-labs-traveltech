from __future__ import annotations

import re
from pathlib import Path

from . import config
from .models import TRIP_ID_PATTERN, Trip

_TRIP_ID_RE = re.compile(TRIP_ID_PATTERN)


def valid_trip_id(trip_id: str | None) -> bool:
    return bool(trip_id) and bool(_TRIP_ID_RE.match(trip_id or ""))


class TripStore:
    """JSON trip storage plus per-trip session ownership.

    Ownership lives in hidden sidecar files so the public ``Trip`` payload
    never carries an owner identifier.  A trip without an owner record is
    treated as inaccessible (legacy demo data must not become public).
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or config.TRIP_STORE_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self._owners = self.root / ".owners"
        self._owners.mkdir(parents=True, exist_ok=True)

    def _safe(self, trip_id: str) -> str:
        return "".join(c for c in trip_id if c.isalnum() or c in "-_")

    def _path(self, trip_id: str) -> Path:
        return self.root / f"{self._safe(trip_id)}.json"

    def _owner_path(self, trip_id: str) -> Path:
        return self._owners / f"{self._safe(trip_id)}.owner"

    def exists(self, trip_id: str) -> bool:
        return valid_trip_id(trip_id) and self._path(trip_id).exists()

    def save(self, trip: Trip) -> Trip:
        path = self._path(trip.id)
        path.write_text(trip.model_dump_json(indent=2), encoding="utf-8")
        return trip

    def get(self, trip_id: str) -> Trip | None:
        if not valid_trip_id(trip_id):
            return None
        path = self._path(trip_id)
        if not path.exists():
            return None
        return Trip.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, trip_id: str) -> bool:
        if not valid_trip_id(trip_id):
            return False
        path = self._path(trip_id)
        if path.exists():
            path.unlink()
            self.release_owner(trip_id)
            return True
        return False

    # ------------------------------------------------------------------ owners
    def set_owner(self, trip_id: str, session_id: str) -> bool:
        """Bind a trip to a session once. Existing owners are never replaced."""
        if not valid_trip_id(trip_id) or not session_id:
            return False
        path = self._owner_path(trip_id)
        try:
            if path.exists():
                return path.read_text(encoding="utf-8").strip() == session_id
            fd_path = path.with_suffix(".tmp")
            fd_path.write_text(session_id, encoding="utf-8")
            fd_path.replace(path)
            return True
        except OSError:
            return False

    def owner_of(self, trip_id: str) -> str | None:
        if not valid_trip_id(trip_id):
            return None
        try:
            return self._owner_path(trip_id).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def release_owner(self, trip_id: str) -> None:
        try:
            self._owner_path(trip_id).unlink()
        except OSError:
            pass

    def get_owned(self, trip_id: str, session_id: str) -> Trip | None:
        if not session_id or self.owner_of(trip_id) != session_id:
            return None
        return self.get(trip_id)

    def delete_owned(self, trip_id: str, session_id: str) -> bool:
        if not session_id or self.owner_of(trip_id) != session_id:
            return False
        return self.delete(trip_id)

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json") if valid_trip_id(p.stem))

    def list_owned(self, session_id: str) -> list[str]:
        if not session_id:
            return []
        found: list[str] = []
        for path in self._owners.glob("*.owner"):
            try:
                if path.read_text(encoding="utf-8").strip() == session_id:
                    found.append(path.stem)
            except OSError:
                continue
        return sorted(found)


__all__ = ["TripStore", "valid_trip_id"]
