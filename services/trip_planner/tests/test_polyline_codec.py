from __future__ import annotations

from services.trip_planner.polyline_codec import decode_polyline, encode_polyline


def test_roundtrip_osrm_precision5() -> None:
    # Classic Google polyline sample
    pts = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    enc = encode_polyline(pts)
    decoded = decode_polyline(enc)
    assert len(decoded) == 3
    for (a, b), (c, d) in zip(pts, decoded):
        assert abs(a - c) < 1e-4
        assert abs(b - d) < 1e-4


def test_decode_empty_and_garbage() -> None:
    assert decode_polyline("") == []
    assert decode_polyline(None) == []  # type: ignore[arg-type]
    # Truncated payload should not raise
    assert isinstance(decode_polyline("_p~iF~ps|U"), list)


def test_decode_does_not_invent_geometry() -> None:
    # Two points only — never invent a third
    enc = encode_polyline([(55.796, 49.106), (55.798, 49.110)])
    assert len(decode_polyline(enc)) == 2
