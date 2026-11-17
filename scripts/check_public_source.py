"""Check tracked files and every reachable Git blob; never print secret values."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub credential": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9_]{25,}|github_pat_[A-Za-z0-9_]{25,})"),
    "API credential": re.compile(rb"\bsk-[A-Za-z0-9_-]{30,}"),
    "Telegram credential": re.compile(rb"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b"),
    "private endpoint": re.compile(rb"(?<![\w.])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?![\d.])"),
    "personal Windows path": re.compile(rb"[A-Za-z]:\\(?:Users|UserData)\\[^\\\s]+", re.I),
}
FORBIDDEN = {".env", ".e2e-credentials.json", ".e2e-fixtures.json"}
EXTENSIONS = {".onnx", ".pt", ".sqlite", ".sqlite3", ".db", ".ovpn", ".p12", ".pfx", ".key", ".zip"}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def scan(label: str, data: bytes) -> list[str]:
    errors = []
    for name, rule in RULES.items():
        for match in rule.finditer(data):
            # Explicitly fictitious tokens required by aiogram's token-format validator.
            if name == "Telegram credential" and b"test" in match.group(0).lower():
                continue
            errors.append(f"{label}: {name}")
    return errors


def main() -> int:
    errors = []
    paths = git("ls-files", "-z").decode().split("\0")
    for name in filter(None, paths):
        path = Path(name)
        errors.extend(scan(name, git("show", ":" + name)))
        if path.name in FORBIDDEN or path.suffix in EXTENSIONS:
            errors.append(f"{name}: forbidden runtime/private artifact")
        if path.name.startswith(".env") and path.name != ".env.example":
            errors.append(f"{name}: private environment file")
    objects = git("rev-list", "--objects", "--all").decode().splitlines()
    checked = 0
    for line in objects:
        sha, _, name = line.partition(" ")
        if git("cat-file", "-t", sha).strip() != b"blob":
            continue
        checked += 1
        errors.extend(scan(name or sha, git("cat-file", "blob", sha)))
    for error in sorted(set(errors)):
        print(error)
    print(f"Checked {checked} reachable blobs; {len(set(errors))} findings.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
