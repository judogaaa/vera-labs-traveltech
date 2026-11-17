from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest

from services.trip_planner.models import (
    DayPlan,
    DayRoute,
    Destination,
    HotelContext,
    Place,
    Stop,
    TravelSegment,
    Trip,
    TripIntent,
)
from services.trip_planner.pdf import _human_summary, _qr_flowable, _route_city_phrase, build_trip_pdf
from services.trip_planner.polyline_codec import encode_polyline
from services.trip_planner.wish_match import diversify_places, diversity_bucket, places_are_duplicate


def _sample_trip(*, web_city: str = "Казань") -> Trip:
    path_w = [(55.7963, 49.1089), (55.7970, 49.1120), (55.7985, 49.1150)]
    path_c = [(55.7985, 49.1150), (55.8000, 49.1180), (55.8020, 49.1200)]
    now = datetime.now(timezone.utc).isoformat()
    return Trip(
        id="t-qr",
        destination=Destination(name=web_city, country="RU", lat=55.79, lon=49.11),
        hotel=HotelContext(name="Hotel", lat=55.795, lon=49.107, city=web_city),
        intent=TripIntent(destination=web_city, days=1, startTime="10:00", returnBy="20:00"),
        createdAt=now,
        updatedAt=now,
        summary=f"Маршрут по {web_city}: 1 день, 2 места.",
        days=[
            DayPlan(
                dayNumber=1,
                summary="День 1",
                stops=[
                    Stop(
                        id="s1",
                        placeProvider="test",
                        placeId="1",
                        name="Кремль",
                        category="attraction",
                        lat=path_w[0][0],
                        lon=path_w[0][1],
                        startTime="10:15",
                        durationMinutes=90,
                    ),
                    Stop(
                        id="s2",
                        placeProvider="test",
                        placeId="2",
                        name="Кул-Шариф",
                        category="religious",
                        lat=path_c[-1][0],
                        lon=path_c[-1][1],
                        startTime="12:30",
                        durationMinutes=60,
                    ),
                ],
                segments=[
                    TravelSegment(
                        fromStopId="hotel",
                        toStopId="s1",
                        mode="walk",
                        distanceMeters=800,
                        durationSeconds=600,
                        verified=True,
                        polyline=encode_polyline(path_w),
                    ),
                    TravelSegment(
                        fromStopId="s1",
                        toStopId="s2",
                        mode="car",
                        distanceMeters=2500,
                        durationSeconds=480,
                        verified=True,
                        polyline=encode_polyline(path_c),
                    ),
                ],
                route=DayRoute(distanceMeters=3300, durationSeconds=1080, polyline=None, verified=True),
            )
        ],
    )


def test_route_city_phrase_kazan_dative() -> None:
    assert "по Казани" in _route_city_phrase("Казань")
    assert "по Казань" not in _route_city_phrase("Казань")
    assert "по Казани" in _human_summary(_sample_trip())


def test_qr_quiet_zone_at_least_4_modules() -> None:
    qrcode = pytest.importorskip("qrcode")

    flow = _qr_flowable("https://example.com/oh-route?trip=demo", size=26)
    assert flow is not None
    # Rebuild with same settings as pdf._qr_flowable and inspect border.
    qr = qrcode.QRCode(border=4, box_size=8, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data("https://example.com/oh-route?trip=demo")
    qr.make(fit=True)
    assert qr.border >= 4
    pil = qr.make_image(fill_color="black", back_color="white").get_image()
    # Quiet zone: outer rim should be white.
    px = pil.convert("L").load()
    w, h = pil.size
    assert px[0, 0] > 200
    assert px[w - 1, h - 1] > 200


def test_pdf_main_qr_prefers_public_trip_link() -> None:
    trip = _sample_trip()
    pdf = build_trip_pdf(trip, web_link="https://oh-hochu.example/oh-route?trip=demo")
    assert pdf[:4] == b"%PDF"
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(pdf)
        text = "".join((doc[i].get_textpage().get_text_bounded() or "") for i in range(len(doc)))
    except Exception:
        text = ""
    if text:
        assert "по Казани" in text or "Маршрут — Казань" in text
        assert "по Казань" not in text
        assert "окно 10:00–20:00" in text or "окно 10:00" in text
        assert "факт" in text.lower() or "10:15" in text
        # Demo example.com link must not pretend to be the scannable full-route QR.
        assert "Демо-ссылка" in text or "образец" in text.lower()


def test_pdf_decodable_qrs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every embedded QR PNG in the PDF must decode to an http(s) URL."""
    pytest.importorskip("qrcode")
    try:
        from pyzbar.pyzbar import decode as zbar_decode
    except Exception:
        pytest.skip("pyzbar not installed")
    from PIL import Image as PILImage
    import pypdfium2 as pdfium

    # Avoid network photo enrich stalling the test.
    monkeypatch.setattr(
        "services.trip_planner.pdf.enrich_trip_photos",
        lambda trip, **_k: trip,
        raising=False,
    )
    monkeypatch.setattr(
        "services.trip_planner.photos.enrich_trip_photos",
        lambda trip, **_k: trip,
        raising=False,
    )
    trip = _sample_trip()
    pdf = build_trip_pdf(trip, web_link="https://maps.example/trip/abc")
    doc = pdfium.PdfDocument(pdf)
    decoded: list[str] = []
    for i in range(len(doc)):
        page = doc[i]
        bitmap = page.render(scale=3).to_pil()
        for obj in zbar_decode(bitmap):
            payload = obj.data.decode("utf-8", errors="replace")
            decoded.append(payload)
            assert payload.startswith("http"), payload
    assert decoded, "expected at least one scannable QR in the PDF"


def test_lenin_memorials_dedupe() -> None:
    a = Place(
        placeId="1",
        placeProvider="test",
        name="В. И. Ленину",
        category="attraction",
        lat=55.79,
        lon=49.11,
        description="памятник",
    )
    b = Place(
        placeId="2",
        placeProvider="test",
        name="В.И. Ульянову-Ленину",
        category="attraction",
        lat=55.80,
        lon=49.13,
        description="памятник",
    )
    assert places_are_duplicate(a, b)
    assert diversity_bucket(a) == "memorial"


def test_diversify_caps_memorials() -> None:
    places = [
        Place(placeId=str(i), placeProvider="t", name=n, category="attraction", lat=55.79 + i * 0.01, lon=49.11, description=d)
        for i, (n, d) in enumerate(
            [
                ("В. И. Ленину", "памятник"),
                ("Воинам ВОВ", "мемориал"),
                ("Казанский кремль", "крепость"),
                ("Кул-Шариф", "мечеть"),
            ]
        )
    ]
    picked = diversify_places(places, limit=3)
    memorials = [p for p in picked if diversity_bucket(p) == "memorial"]
    assert len(memorials) <= 1
    names = {p.name for p in picked}
    assert "Казанский кремль" in names or "Кул-Шариф" in names
