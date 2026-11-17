"""Typographic helpers: Arabic RTL shaping + safe PDF paragraph text."""
from __future__ import annotations

import re

_ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)


def contains_arabic(text: str) -> bool:
    return bool(text and _ARABIC_RE.search(text))


def shape_for_pdf(text: str) -> str:
    """Reshape Arabic for ReportLab (no native RTL). Other scripts pass through."""
    if not text:
        return ""
    if not contains_arabic(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:  # noqa: BLE001
        return text


def pdf_safe(text: str) -> str:
    """Escape XML entities after shaping."""
    shaped = shape_for_pdf(text or "")
    return (
        shaped.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
