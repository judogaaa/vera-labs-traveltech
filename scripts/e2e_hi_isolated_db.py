"""Copy demo SQLite to an isolated path for Playwright live E2E (no demo pollution)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "ostrovok_demo" / "intelligence.sqlite"
DST_DIR = ROOT / "artifacts" / "e2e" / "hi_isolated"
DST = DST_DIR / "intelligence.sqlite"


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    DST_DIR.mkdir(parents=True, exist_ok=True)
    # Also copy companion files if present
    for name in ("intelligence.sqlite", "intelligence.sqlite-wal", "intelligence.sqlite-shm"):
        s = SRC.parent / name
        if s.exists():
            shutil.copy2(s, DST_DIR / name)
    print(str(DST.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
