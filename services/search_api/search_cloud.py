from __future__ import annotations

import io
import time
from typing import Any

from PIL import Image

from . import config


_identity_encoder = None
_similarity_encoder = None


def indexer_available() -> bool:
    """True when the optional services/indexer package can be imported."""
    try:
        import importlib.util

        return importlib.util.find_spec("indexer") is not None
    except Exception:  # noqa: BLE001
        return False


def get_identity_encoder():
    # Optional ML/indexer package is not committed to every checkout.
    # Import lazily so the trip planner and catalog API can still start.
    if not indexer_available():
        raise ModuleNotFoundError(
            "services.indexer is not available. Set SEARCH_BACKEND=mock for local demo."
        )
    from indexer.encoders.registry import get_encoder

    global _identity_encoder
    if _identity_encoder is None:
        # Hotel-specific encoder for identity collection (env override; CLIP fallback)
        name = (config.IDENTITY_ENCODER or "hotels50k-official").strip() or "hotels50k-official"
        try:
            _identity_encoder = get_encoder(name)
        except Exception:
            _identity_encoder = get_encoder("clip")
    return _identity_encoder


def get_similarity_encoder():
    if not indexer_available():
        raise ModuleNotFoundError(
            "services.indexer is not available. Set SEARCH_BACKEND=mock for local demo."
        )
    from indexer.encoders.registry import get_encoder

    global _similarity_encoder
    if _similarity_encoder is None:
        _similarity_encoder = get_encoder("clip")
    return _similarity_encoder


def search_by_image_bytes(
    data: bytes,
    *,
    top_k_images: int = 40,
    top_k_hotels: int = 8,
    collection: str | None = None,
) -> dict[str, Any]:
    if not indexer_available():
        raise ModuleNotFoundError(
            "services.indexer is not available. Set SEARCH_BACKEND=mock for local demo."
        )
    from indexer.qdrant_ops import search_vectors

    started = time.perf_counter()
    collection = collection or config.QDRANT_COLLECTION_IDENTITY
    image = Image.open(io.BytesIO(data)).convert("RGB")

    if collection == config.QDRANT_COLLECTION_SIMILARITY:
        encoder = get_similarity_encoder()
    else:
        encoder = get_identity_encoder()

    vector = encoder.embed_image(image)
    hits = search_vectors(
        collection,
        vector,
        limit=top_k_images,
        with_payload=True,
    )

    grouped: dict[str, dict[str, Any]] = {}
    for hit in hits:
        payload = hit.payload or {}
        hotel_id = str(payload.get("hotel_id") or "")
        if not hotel_id:
            continue
        current = grouped.get(hotel_id)
        score = float(hit.score)
        if current is None or score > current["score"]:
            grouped[hotel_id] = {
                "hotel_id": hotel_id,
                "hotel_name": payload.get("hotel_name"),
                "chain": payload.get("chain"),
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
                "score": score,
                "matchedImage": {
                    "image_id": payload.get("image_id"),
                    "source_reference": payload.get("source_reference"),
                    "image_url": payload.get("image_url"),
                    "dataset_split": payload.get("dataset_split"),
                    "provider": payload.get("provider"),
                    "score": score,
                },
            }

    hotels = sorted(grouped.values(), key=lambda x: x["score"], reverse=True)[:top_k_hotels]
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "backend": "cloud",
        "collection": collection,
        "encoder": encoder.name,
        "elapsed_ms": round(elapsed_ms, 2),
        "image_hits": len(hits),
        "hotels": hotels,
    }
