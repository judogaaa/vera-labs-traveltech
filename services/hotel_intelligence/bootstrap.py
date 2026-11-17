"""Load demo hotels.json (+ optional observations.jsonl) into the store."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import config
from .attributes.definitions import build_default_registry
from .store import IntelligenceStore


def bootstrap(
    demo_dir: Path | str | None = None,
    *,
    db_path: Path | str | None = None,
    store: IntelligenceStore | None = None,
) -> dict[str, Any]:
    root = Path(demo_dir) if demo_dir else config.DEMO_DIR
    st = store or IntelligenceStore(db_path=db_path)
    registry = build_default_registry()
    for key in registry.keys():
        st.upsert_attribute_definition(registry.get(key))
    counts = st.seed_from_demo_dir(root)
    return {
        "demo_dir": str(root),
        "db_path": str(st.db_path),
        "hotels": counts["hotels"],
        "observations": counts["observations"],
        "attributes": len(registry.keys()),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(bootstrap(), ensure_ascii=False, indent=2))
