from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Allow importing shared indexer embedding helpers
SERVICES_DIR = Path(__file__).resolve().parents[1]
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))

QDRANT_URL = os.getenv("QDRANT_URL", "").rstrip("/")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION_IDENTITY = os.getenv(
    "QDRANT_COLLECTION_IDENTITY", "hotel_identity_resnetv2_10k"
)
QDRANT_COLLECTION_SIMILARITY = os.getenv("QDRANT_COLLECTION_SIMILARITY", "hotel_similarity")
IDENTITY_ENCODER = os.getenv("IDENTITY_ENCODER", "hotels50k-official")
SEARCH_BACKEND = os.getenv("SEARCH_BACKEND", "cloud").lower()
_LOCAL_CLIP = Path(__file__).resolve().parents[1] / "indexer" / "models" / "clip-vit-base-patch32"
EMBEDDING_MODEL_ID = os.getenv(
    "EMBEDDING_MODEL_ID",
    str(_LOCAL_CLIP) if (_LOCAL_CLIP / "pytorch_model.bin").exists() else "openai/clip-vit-base-patch32",
)
