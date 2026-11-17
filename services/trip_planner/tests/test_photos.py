from __future__ import annotations

import time
from unittest.mock import patch

from services.trip_planner.models import Place
from services.trip_planner.photos import (
    commons_file_url,
    enrich_places,
    fetch_image_bytes,
    resolve_photo_ref,
    _trusted_image_url,
    _SafeImageRedirect,
)


def test_commons_file_url_from_title() -> None:
    url = commons_file_url("File:Kazan Kremlin Spasskaya Tower.jpg", width=640)
    assert url is not None
    assert url.startswith("https://commons.wikimedia.org/wiki/Special:FilePath/")
    assert "width=640" in url
    assert "Category:" not in (commons_file_url("Category:Kazan") or "")


def test_commons_file_url_https_passthrough() -> None:
    src = "https://commons.wikimedia.org/wiki/Special:FilePath/Foo.jpg"
    url = commons_file_url(src, width=320)
    assert url is not None
    assert url.startswith("https://")
    assert "width=320" in url


def test_resolve_photo_ref_drops_category() -> None:
    assert resolve_photo_ref("Category:Museums") is None


def test_resolve_photo_ref_file_title() -> None:
    url = resolve_photo_ref("File:Example.jpg")
    assert url is not None
    assert "Special:FilePath" in url


def test_fetch_image_bytes_rejects_http() -> None:
    assert fetch_image_bytes("http://example.com/x.jpg") is None


def test_fetch_image_bytes_timeout(monkeypatch) -> None:
    def _slow(*_a, **_k):
        raise TimeoutError("slow")

    class _FailingOpener:
        def open(self, *_a, **_k):
            return _slow()

    monkeypatch.setattr("urllib.request.build_opener", lambda *_a, **_k: _FailingOpener())
    assert fetch_image_bytes("https://upload.wikimedia.org/x.jpg", timeout=0.2) is None


def test_image_url_rejects_non_wikimedia_and_private_servers() -> None:
    assert _trusted_image_url("https://commons.wikimedia.org/wiki/Special:FilePath/Foo.jpg")
    assert _trusted_image_url("https://upload.wikimedia.org/example.jpg")
    for url in (
        "https://127.0.0.1/photo.jpg",
        "https://169.254.169.254/latest/meta-data/",
        "https://localhost/photo.jpg",
        "https://commons.wikimedia.org.evil.test/p.jpg",
        "https://bad:password@commons.wikimedia.org/p.jpg",
        "https://upload.wikimedia.org:8443/p.jpg",
        "http://upload.wikimedia.org/p.jpg",
        "https://example.com/p.jpg",
    ):
        assert not _trusted_image_url(url)
        assert fetch_image_bytes(url) is None


def test_photo_redirect_cannot_leave_allowed_hosts() -> None:
    from urllib.request import Request
    handler = _SafeImageRedirect()
    req = Request("https://commons.wikimedia.org/wiki/Special:FilePath/Foo.jpg")
    assert handler.redirect_request(
        req, None, 302, "Found", {}, "https://127.0.0.1/private"
    ) is None


def test_enrich_places_respects_hard_timeout() -> None:
    places = [
        Place(
            placeProvider="t",
            placeId=str(i),
            name=f"P{i}",
            category="attraction",
            lat=55.0,
            lon=49.0,
            photoUrl="File:Example.jpg",
            wikidataId="Q123",
        )
        for i in range(8)
    ]

    def _hang(*_a, **_k):
        time.sleep(2.0)
        return None

    with patch("services.trip_planner.photos.wikidata_p18_url", side_effect=_hang):
        with patch("services.trip_planner.photos.resolve_photo_ref", side_effect=_hang):
            t0 = time.perf_counter()
            out = enrich_places(places, timeout_s=0.4)
            elapsed = time.perf_counter() - t0
    assert len(out) == 8
    # Must return within a bounded window (not hang on sleep(2)*8)
    assert elapsed < 1.5
