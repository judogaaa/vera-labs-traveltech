"""Validate hotel query images before GigaChat Vision upload."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

ALLOWED_MIME = frozenset({"image/jpeg", "image/png", "image/bmp", "image/tiff"})
MAX_BYTES = 12 * 1024 * 1024  # under GigaChat 15 MB limit with headroom
MIN_SIDE = 32
MAX_SIDE = 8192


@dataclass
class ValidatedImage:
    data: bytes
    mime: str
    width: int
    height: int
    filename: str


def sniff_mime(data: bytes) -> str | None:
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 2 and data[:2] == b"BM":
        return "image/bmp"
    if len(data) >= 4 and data[:4] in {b"II*\x00", b"MM\x00*"}:
        return "image/tiff"
    return None


def validate_image_bytes(
    data: bytes,
    *,
    declared_mime: str | None = None,
    filename: str | None = None,
) -> ValidatedImage:
    if not data:
        raise ValueError("empty_image")
    if len(data) > MAX_BYTES:
        raise ValueError("image_too_large")
    mime = sniff_mime(data)
    if mime is None:
        raise ValueError("unsupported_or_corrupt_image")
    if declared_mime and declared_mime.split(";")[0].strip().lower() not in ALLOWED_MIME:
        # Prefer sniffed mime; reject if declared is wildly wrong
        declared = declared_mime.split(";")[0].strip().lower()
        if declared not in ALLOWED_MIME and declared != "application/octet-stream":
            raise ValueError("mime_not_allowed")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im2:
            width, height = im2.size
            if width < MIN_SIDE or height < MIN_SIDE:
                raise ValueError("image_too_small")
            if width > MAX_SIDE or height > MAX_SIDE:
                raise ValueError("image_resolution_too_large")
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"image_decode_failed:{type(exc).__name__}") from exc

    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/bmp": "bmp",
        "image/tiff": "tiff",
    }.get(mime, "bin")
    safe_name = (filename or f"query.{ext}").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in safe_name:
        safe_name = f"{safe_name}.{ext}"
    return ValidatedImage(
        data=data,
        mime=mime,
        width=width,
        height=height,
        filename=safe_name[:80],
    )


def reject_remote_image_url(image_url: str | None) -> None:
    """SSRF guard: never fetch arbitrary client-supplied URLs for Vision."""
    if image_url is not None and str(image_url).strip():
        raise ValueError("image_url_forbidden_ssrf_use_multipart_upload")


def proof_safe_meta(
    *,
    model: str | None,
    file_id: str | None,
    bytes_len: int,
    mime: str,
    width: int,
    height: int,
    vision_used: bool,
    content_preview: str | None = None,
) -> dict[str, Any]:
    """Evidence for acceptance — never includes raw image or secrets."""
    preview = (content_preview or "")[:240]
    return {
        "vision_used": vision_used,
        "model": model,
        "file_id_prefix": (file_id or "")[:8] if file_id else None,
        "bytes": bytes_len,
        "mime": mime,
        "width": width,
        "height": height,
        "attachments_sent": bool(file_id),
        "content_preview": preview,
    }
