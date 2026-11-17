"""Google Encoded Polyline Algorithm (precision 5) — used by OSRM overview geometry."""
from __future__ import annotations


def decode_polyline(encoded: str, *, precision: int = 5) -> list[tuple[float, float]]:
    """Decode to list of (lat, lon). Empty / invalid input → []."""
    if not encoded or not isinstance(encoded, str):
        return []
    factor = 10**precision
    coords: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lon = 0
    length = len(encoded)
    try:
        while index < length:
            # latitude
            result = 0
            shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            dlat = ~(result >> 1) if (result & 1) else (result >> 1)
            lat += dlat
            # longitude
            result = 0
            shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            dlon = ~(result >> 1) if (result & 1) else (result >> 1)
            lon += dlon
            coords.append((lat / factor, lon / factor))
    except (IndexError, ValueError, TypeError):
        return coords
    return coords


def encode_polyline(coords: list[tuple[float, float]], *, precision: int = 5) -> str:
    """Encode (lat, lon) list — used in tests."""
    factor = 10**precision

    def _enc(value: int) -> str:
        value = ~(value << 1) if value < 0 else (value << 1)
        chars: list[str] = []
        while value >= 0x20:
            chars.append(chr((0x20 | (value & 0x1F)) + 63))
            value >>= 5
        chars.append(chr(value + 63))
        return "".join(chars)

    out: list[str] = []
    prev_lat = 0
    prev_lon = 0
    for lat, lon in coords:
        ilat = int(round(lat * factor))
        ilon = int(round(lon * factor))
        out.append(_enc(ilat - prev_lat))
        out.append(_enc(ilon - prev_lon))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)
