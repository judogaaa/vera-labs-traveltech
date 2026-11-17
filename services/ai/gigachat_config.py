from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

GIGACHAT_AUTH_KEY = (
    os.getenv("GIGACHAT_AUTH_KEY", "").strip()
    or os.getenv("GIGACHAT_CREDENTIALS", "").strip()
)
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip()
GIGACHAT_BASE_URL = os.getenv("GIGACHAT_BASE_URL", "https://api.giga.chat").rstrip("/")
GIGACHAT_AUTH_URL = os.getenv(
    "GIGACHAT_AUTH_URL",
    "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
).strip()
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "").strip()
GIGACHAT_ENABLED = os.getenv("GIGACHAT_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
GIGACHAT_CA_BUNDLE = (
    os.getenv("GIGACHAT_CA_BUNDLE", "").strip()
    or os.getenv("GIGACHAT_CA_BUNDLE_FILE", "").strip()
)
# Resolve relative CA path against repo root
if GIGACHAT_CA_BUNDLE and not Path(GIGACHAT_CA_BUNDLE).is_absolute():
    candidate = _ROOT / GIGACHAT_CA_BUNDLE
    if candidate.exists():
        GIGACHAT_CA_BUNDLE = str(candidate)
GIGACHAT_TIMEOUT = float(os.getenv("GIGACHAT_TIMEOUT", "45"))
GIGACHAT_MAX_RETRIES = int(os.getenv("GIGACHAT_MAX_RETRIES", "3"))
# Temporary local diagnostic only — never default True in production
GIGACHAT_TLS_INSECURE = os.getenv("GIGACHAT_TLS_INSECURE", "0").strip() in {
    "1",
    "true",
    "yes",
}


def require_enabled_credentials() -> None:
    if GIGACHAT_ENABLED and not GIGACHAT_AUTH_KEY:
        raise RuntimeError(
            "GIGACHAT_ENABLED=true but GIGACHAT_AUTH_KEY is missing. "
            "Set the Authorization key in root .env (never commit it)."
        )
