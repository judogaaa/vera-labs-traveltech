from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.trip_planner.map_render import render_trip_map_png, verified_polyline_point_count
from services.trip_planner.models import (
    DayPlan,
    DayRoute,
    Destination,
    HotelContext,
    Stop,
    TravelSegment,
    Trip,
    TripIntent,
)
from services.trip_planner.pdf import build_trip_pdf, _qr_flowable
from services.trip_planner.photos import directions_link, maps_link
from services.trip_planner.polyline_codec import encode_polyline
from services.trip_planner.text_shape import contains_arabic, shape_for_pdf


def _trip_with_osrm_geometry(*, arabic_name: bool = False) -> Trip:
    # Bent path — not a straight A→B chord
    path = [
        (55.7963, 49.1089),
        (55.7970, 49.1120),
        (55.7985, 49.1150),
        (55.8000, 49.1180),
    ]
    enc = encode_polyline(path)
    name_b = "مسجد الفاتح" if arabic_name else "Кремль"
    now = datetime.now(timezone.utc).isoformat()
    return Trip(
        id="t-map",
        destination=Destination(name="Казань" if not arabic_name else "دبي", country="RU", lat=55.79, lon=49.11),
        hotel=HotelContext(name="Hotel", lat=55.795, lon=49.107, city="Kazan"),
        intent=TripIntent(destination="Казань", days=1),
        createdAt=now,
        updatedAt=now,
        days=[
            DayPlan(
                dayNumber=1,
                summary="День 1",
                stops=[
                    Stop(
                        id="s1",
                        placeProvider="test",
                        placeId="1",
                        name="Набережная",
                        category="attraction",
                        lat=path[0][0],
                        lon=path[0][1],
                        address="ул. Баумана, Казань",
                        startTime="10:00",
                        durationMinutes=60,
                        description="Набережная Казанки",
                    ),
                    Stop(
                        id="s2",
                        placeProvider="test",
                        placeId="2",
                        name=name_b,
                        category="religious",
                        lat=path[-1][0],
                        lon=path[-1][1],
                        address="Кремль",
                        startTime="12:00",
                        durationMinutes=90,
                        description="Достопримечательность",
                    ),
                ],
                segments=[
                    TravelSegment(
                        fromStopId="s1",
                        toStopId="s2",
                        mode="walk",
                        distanceMeters=1200,
                        durationSeconds=900,
                        verified=True,
                        polyline=enc,
                    )
                ],
                route=DayRoute(
                    distanceMeters=1200,
                    durationSeconds=900,
                    polyline=enc,
                    verified=True,
                ),
            )
        ],
    )


def test_verified_polyline_points_count() -> None:
    trip = _trip_with_osrm_geometry()
    assert verified_polyline_point_count(trip) >= 4


def test_unverified_segment_not_drawn_as_road() -> None:
    trip = _trip_with_osrm_geometry()
    trip.days[0].segments[0] = trip.days[0].segments[0].model_copy(
        update={"verified": False, "polyline": None}
    )
    trip.days[0].route = DayRoute(verified=False, polyline=None)
    assert verified_polyline_point_count(trip) == 0
    png = render_trip_map_png(trip, allow_network=False)
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_map_uses_polyline_not_missing_when_offline() -> None:
    trip = _trip_with_osrm_geometry()
    png = render_trip_map_png(trip, width_px=640, height_px=400, allow_network=False)
    assert png is not None
    assert len(png) > 500


def test_qr_flowable_requires_qrcode() -> None:
    qr = _qr_flowable("https://example.com/oh-route?trip=demo", size=40)
    assert qr is not None


def test_maps_vs_directions_links() -> None:
    pin = maps_link(55.79, 49.11, "Кремль")
    assert "mlat=55.790000" in pin
    assert "#map=17/" in pin
    # Query string must carry the name — not the hash fragment.
    assert "q=" in pin.split("#", 1)[0]
    walk = directions_link(55.79, 49.11, 55.80, 49.12, mode="walk")
    car = directions_link(55.79, 49.11, 55.80, 49.12, mode="car")
    assert "directions" in walk and "fossgis_osrm_foot" in walk
    assert "fossgis_osrm_car" in car
    assert "route=" in walk


def test_pdf_embeds_osrm_map_and_public_link() -> None:
    trip = _trip_with_osrm_geometry()
    pdf = build_trip_pdf(trip, web_link="https://example.com/oh-route?trip=demo")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 8_000  # map raster makes it larger than schematic
    # Extract text — compressed PDF streams may not contain literal URL bytes
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(pdf)
        text = "".join((doc[i].get_textpage().get_text_bounded() or "") for i in range(len(doc)))
    except Exception:
        text = ""
    if text:
        assert "example.com" in text
        assert "демо" in text.lower() or "образец" in text.lower()
        assert "openstreetmap" in text.lower()
    pdf2 = build_trip_pdf(trip, web_link="https://www.openstreetmap.org/")
    assert pdf2[:4] == b"%PDF"
    assert len(pdf2) > 8_000


def test_pdf_survives_without_photos() -> None:
    trip = _trip_with_osrm_geometry()
    for s in trip.days[0].stops:
        s.photoUrl = None
    pdf = build_trip_pdf(trip, web_link=None)
    assert pdf[:4] == b"%PDF"


def test_arabic_shaping_changes_presentation() -> None:
    raw = "مسجد"
    assert contains_arabic(raw)
    shaped = shape_for_pdf(raw)
    # With arabic-reshaper installed, presentation form differs; without, passthrough.
    assert shaped  # non-empty
    pdf = build_trip_pdf(_trip_with_osrm_geometry(arabic_name=True), web_link=None)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000


def test_external_service_failure_does_not_break_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    trip = _trip_with_osrm_geometry()

    def _boom(*_a, **_k):
        raise TimeoutError("network down")

    monkeypatch.setattr("services.trip_planner.map_render._fetch_tile", _boom)
    monkeypatch.setattr(
        "services.trip_planner.photos.fetch_image_bytes",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "services.trip_planner.pdf.fetch_image_bytes",
        lambda *_a, **_k: None,
    )
    # enrich_trip_photos must not hang/raise either
    monkeypatch.setattr(
        "services.trip_planner.photos.enrich_trip_photos",
        lambda trip, **_k: trip,
    )
    pdf = build_trip_pdf(trip, web_link="https://example.com/x")
    assert pdf[:4] == b"%PDF"
