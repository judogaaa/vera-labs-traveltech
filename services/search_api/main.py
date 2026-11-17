from __future__ import annotations

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .search_cloud import (
    get_identity_encoder,
    get_similarity_encoder,
    indexer_available,
    search_by_image_bytes,
)

# curated catalog router (services/catalog)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from services.catalog.api import router as catalog_router  # noqa: E402
from services.catalog.hotel_resolver import HotelResolver  # noqa: E402
from services.trip_planner.api import router as trip_planner_router  # noqa: E402
from services.hotel_intelligence.api import router as hotel_intelligence_router  # noqa: E402
from services.ai.gigachat_config import require_enabled_credentials  # noqa: E402

# Fail-fast when GigaChat is enabled without credentials
require_enabled_credentials()

_encoder_warm: dict[str, str] = {"status": "pending", "detail": ""}


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001, ANN201
    # Do not block HTTP (health/ready) on ML load — warm in background when useful.
    async def _warm() -> None:
        if config.SEARCH_BACKEND != "cloud" or not indexer_available():
            _encoder_warm["status"] = "skipped"
            _encoder_warm["detail"] = (
                "SEARCH_BACKEND!=cloud or services.indexer unavailable"
            )
            return
        t0 = time.perf_counter()
        _encoder_warm["status"] = "warming"
        for loader in (get_identity_encoder, get_similarity_encoder):
            try:
                await run_in_threadpool(loader)
            except Exception as exc:  # noqa: BLE001
                _encoder_warm["status"] = "failed"
                _encoder_warm["detail"] = f"{type(exc).__name__}: {exc}"
                return
        _encoder_warm["status"] = "ready"
        _encoder_warm["detail"] = f"warmed in {(time.perf_counter() - t0) * 1000:.0f}ms"
        print(f"encoders {_encoder_warm['detail']}", flush=True)

    task = asyncio.create_task(_warm())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="vera-labs visual search", version="0.1.0", lifespan=lifespan)
# Local UI: credentialed CORS for HI demo-session cookie (loopback origins only).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(catalog_router)
app.include_router(trip_planner_router)
app.include_router(hotel_intelligence_router)
_hotel_resolver = HotelResolver()


def _catalog_status() -> dict:
    try:
        db = _hotel_resolver.load()
        return {
            "ok": True,
            "hotels": len(db.get("hotels") or []),
            "catalog": "configured",
        }
    except FileNotFoundError:
        return {"ok": False, "error": "catalog_missing"}
    except Exception:  # noqa: BLE001
        # Readiness is public. Never expose absolute paths or exception text.
        return {"ok": False, "error": "catalog_unavailable"}


@app.get("/health")
def health() -> dict:
    """Liveness: process is up. Does not load ML or touch Qdrant."""
    return {"ok": True, "status": "alive"}


@app.get("/ready")
def ready() -> dict:
    """Readiness: dependency snapshot without heavy ML work per request."""
    catalog = _catalog_status()
    idx = indexer_available()
    backend = config.SEARCH_BACKEND
    degraded: list[str] = []
    if not catalog.get("ok"):
        degraded.append("catalog_missing")
    if backend == "cloud" and not idx:
        degraded.append("indexer_unavailable")
    if backend == "cloud" and (not config.QDRANT_URL or not config.QDRANT_API_KEY):
        degraded.append("qdrant_env_missing")
    if _encoder_warm.get("status") == "failed":
        degraded.append("encoder_warm_failed")

    # Catalog is always required for this API surface. Cloud visual-search extras
    # degrade readiness but trips/catalog can still serve when SEARCH_BACKEND=mock.
    ready_ok = catalog.get("ok") is True and (
        backend != "cloud"
        or (idx and bool(config.QDRANT_URL) and bool(config.QDRANT_API_KEY))
    )
    payload = {
        "ok": ready_ok,
        "status": "ready" if ready_ok else "not_ready",
        "search_backend": backend,
        "indexer_available": idx,
        "encoder_warm": dict(_encoder_warm),
        "catalog": catalog,
        "collections": {
            "identity": config.QDRANT_COLLECTION_IDENTITY,
            "similarity": config.QDRANT_COLLECTION_SIMILARITY,
        },
        "degraded": degraded,
        "security": {
            "auth": "signed-http-only-session",
            "note": (
                "Trip endpoints require a signed HttpOnly session cookie; "
                "each trip is readable only by the session that created it."
            ),
        },
    }
    if not ready_ok:
        raise HTTPException(status_code=503, detail=payload)
    return payload


@app.post("/api/visual-search")
async def visual_search(
    file: UploadFile = File(...),
    mode: str = "full-image",
) -> dict:
    # Do not read unbounded multipart image data into server memory.
    max_bytes = 10 * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")

    backend = config.SEARCH_BACKEND
    # full-image / hotel identity → ResNet + QDRANT_COLLECTION_IDENTITY
    # freehand/selected region (lasso) → CLIP + hotel_similarity
    region_modes = {"freehand-region", "selected-region", "lasso", "region", "similarity"}
    use_similarity = mode in region_modes
    collection = (
        config.QDRANT_COLLECTION_SIMILARITY
        if use_similarity
        else config.QDRANT_COLLECTION_IDENTITY
    )

    if backend == "cloud":
        if not config.QDRANT_URL or not config.QDRANT_API_KEY:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "qdrant_not_configured",
                    "message": "Qdrant env is not configured. Set SEARCH_BACKEND=mock for local demo.",
                },
            )
        if not indexer_available():
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "indexer_unavailable",
                    "message": (
                        "services.indexer is not installed in this checkout. "
                        "Use SEARCH_BACKEND=mock for local demo, or install the indexer package."
                    ),
                },
            )
        try:
            result = await run_in_threadpool(search_by_image_bytes, data, collection=collection)
            result["mode"] = mode
            enriched = []
            for hit in result.get("hotels") or []:
                item = dict(hit)
                ds_id = str(item.get("hotel_id") or item.get("id") or "")
                try:
                    resolved = _hotel_resolver.resolve_hotels50k(ds_id) if ds_id else None
                except FileNotFoundError:
                    resolved = None
                if resolved:
                    item["curated"] = resolved["card"]
                    item["curated_match"] = resolved["match"]
                enriched.append(item)
            result["hotels"] = enriched
            return result
        except Exception as exc:  # noqa: BLE001
            # Honest failure — do not invent cloud matches.
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "cloud_search_failed",
                    "message": (
                        f"Cloud search failed ({type(exc).__name__}). "
                        "Use SEARCH_BACKEND=mock for local demo."
                    ),
                },
            ) from exc

    # mock mode: intentionally empty cloud hotels; frontend keeps existing mock path
    return {
        "backend": "mock",
        "mode": mode,
        "hotels": [],
        "message": "Mock mode active — use frontend local catalog retrieval",
    }


@app.post("/api/visual-search/gigachat-assist")
async def visual_search_gigachat_assist(
    file: UploadFile | None = File(default=None),
    image_url: str | None = None,
    crop_hint: str | None = None,
    mode: str = "full-image",
) -> dict:
    """GigaChat Vision assist via multipart image → /v1/files + attachments.

    Never fetches client image_url (SSRF). Never replaces ResNet/CLIP identity.
    ``vision_invoked`` is true only when a file id was attached to chat.
    """
    from services.hotel_intelligence.gigachat_nlu import describe_image_features

    # Explicit SSRF deny even if Form binds a string
    if image_url is not None and str(image_url).strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "image_url_forbidden",
                "message": "Pass the image as multipart file; remote URLs are rejected.",
            },
        )

    if file is None:
        raise HTTPException(status_code=400, detail="file_required")

    max_bytes = 12 * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds 12 MB assist limit")

    hint = crop_hint or (
        "выделенный фрагмент"
        if mode in {"freehand-region", "selected-region", "lasso", "region"}
        else "полный кадр"
    )
    declared = file.content_type
    fname = file.filename or "query.jpg"

    def _run_assist() -> dict | None:
        return describe_image_features(
            image_bytes=data,
            crop_hint=hint,
            declared_mime=declared,
            filename=fname,
        )

    assist = await run_in_threadpool(_run_assist)
    if assist is None:
        return {
            "assist": None,
            "model_invoked": False,
            "vision_invoked": False,
            "limitation": "gigachat_not_configured",
            "note": "Visual identity still comes from ResNet/CLIP + Qdrant when configured.",
        }
    return {
        "assist": assist,
        "model_invoked": bool(assist.get("model_invoked")),
        "vision_invoked": bool(assist.get("vision_invoked")),
        "unsupported": bool(assist.get("unsupported")),
        "limitation": assist.get("limitation"),
        "model": assist.get("model"),
        "proof": assist.get("proof"),
        "note": "Assistive only — does not override visual match scores.",
    }
