"""Raster overview map for PDF: OSM basemap tiles + verified OSRM polylines by mode."""
from __future__ import annotations

import hashlib
import io
import math
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import Trip
from .photos import UA
from .polyline_codec import decode_polyline

# OSM raster tiles — permitted for limited offline PDF embeds with attribution.
TILE_URLS = (
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
)
TILE_SIZE = 256
MAX_TILES = 36
TILE_TIMEOUT = 2.8
ATTRIBUTION = "© OpenStreetMap contributors"
TILE_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "map_tile_cache"

# Walk = brand blue, car = navy (never draw car geometry in walk style alone)
COLOR_WALK = ((14, 65, 210), (194, 239, 158))
COLOR_CAR = ((14, 23, 77), (255, 180, 90))


def _lon_to_x(lon: float, z: int) -> float:
    return (lon + 180.0) / 360.0 * (2**z)


def _lat_to_y(lat: float, z: int) -> float:
    lat = max(min(lat, 85.05112878), -85.05112878)
    rad = math.radians(lat)
    return (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * (2**z)


def _choose_zoom(min_lon: float, max_lon: float, min_lat: float, max_lat: float, px_w: int, px_h: int) -> int:
    for z in range(16, 9, -1):
        x0, x1 = _lon_to_x(min_lon, z), _lon_to_x(max_lon, z)
        y0, y1 = _lat_to_y(max_lat, z), _lat_to_y(min_lat, z)
        tw = max(1, int(math.ceil(x1) - math.floor(x0)))
        th = max(1, int(math.ceil(y1) - math.floor(y0)))
        if tw * th <= MAX_TILES and tw * TILE_SIZE >= px_w * 0.55 and th * TILE_SIZE >= px_h * 0.55:
            return z
    return 11


def _tile_cache_path(z: int, x: int, y: int) -> Path:
    key = hashlib.sha1(f"{z}/{x}/{y}".encode()).hexdigest()[:20]
    return TILE_CACHE_DIR / f"{z}_{x}_{y}_{key}.png"


def _normalize_tile(img: Image.Image) -> Image.Image:
    """Force exact OSM tile size so paste seams stay aligned."""
    rgb = img.convert("RGB")
    if rgb.size != (TILE_SIZE, TILE_SIZE):
        rgb = rgb.resize((TILE_SIZE, TILE_SIZE), Image.Resampling.NEAREST)
    return rgb


def _map_caption_font(size: int = 14) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidates = (
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    )
    for path in candidates:
        try:
            if path.exists():
                return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fetch_tile(z: int, x: int, y: int) -> Image.Image | None:
    cache_path = _tile_cache_path(z, x, y)
    try:
        if cache_path.exists() and cache_path.stat().st_size > 80:
            return _normalize_tile(Image.open(cache_path))
    except OSError:
        pass

    for tmpl in TILE_URLS:
        url = tmpl.format(z=z, x=x, y=y)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TILE_TIMEOUT) as resp:
                data = resp.read()
            if len(data) < 80 or len(data) > 2_000_000:
                continue
            # Keep uniform water/land tiles — rejecting them left white mosaic gaps.
            img = _normalize_tile(Image.open(io.BytesIO(data)))
            try:
                TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                img.save(cache_path, format="PNG")
            except OSError:
                pass
            return img
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
            continue
    return None


def _collect_route_paths(trip: Trip) -> list[tuple[str, list[tuple[float, float]]]]:
    """Return (mode, latlon_path) for verified legs only — never invent roads."""
    paths: list[tuple[str, list[tuple[float, float]]]] = []
    for day in trip.days:
        # Prefer per-leg geometry so mixed modes stay distinguishable.
        leg_paths: list[tuple[str, list[tuple[float, float]]]] = []
        for seg in day.segments:
            if getattr(seg, "verified", True) is False:
                continue
            enc = getattr(seg, "polyline", None)
            if not enc:
                continue
            pts = decode_polyline(enc)
            if len(pts) >= 2:
                leg_paths.append((seg.mode or "walk", pts))
        if leg_paths:
            paths.extend(leg_paths)
            continue
        day_poly = getattr(day.route, "polyline", None)
        if day_poly and getattr(day.route, "verified", True):
            pts = decode_polyline(day_poly)
            if len(pts) >= 2:
                modes = {s.mode for s in day.segments if s.verified} or {"walk"}
                mode = next(iter(modes)) if len(modes) == 1 else "walk"
                paths.append((mode, pts))
    return paths


def _bbox(trip: Trip, paths: list[tuple[str, list[tuple[float, float]]]]) -> tuple[float, float, float, float] | None:
    lats: list[float] = []
    lons: list[float] = []
    for _mode, path in paths:
        for lat, lon in path:
            lats.append(lat)
            lons.append(lon)
    for day in trip.days:
        for s in day.stops:
            lats.append(s.lat)
            lons.append(s.lon)
    if trip.hotel and trip.hotel.lat is not None and trip.hotel.lon is not None:
        lats.append(float(trip.hotel.lat))
        lons.append(float(trip.hotel.lon))
    if not lats or not lons:
        return None
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    pad_lat = max((max_lat - min_lat) * 0.14, 0.004)
    pad_lon = max((max_lon - min_lon) * 0.14, 0.004)
    return min_lon - pad_lon, max_lon + pad_lon, min_lat - pad_lat, max_lat + pad_lat


def render_trip_map_png(
    trip: Trip,
    *,
    width_px: int = 1200,
    height_px: int = 760,
    allow_network: bool = True,
) -> bytes | None:
    """Build an overview PNG. Unverified legs are never drawn as roads."""
    paths = _collect_route_paths(trip)
    box = _bbox(trip, paths)
    if box is None:
        return None
    min_lon, max_lon, min_lat, max_lat = box

    z = _choose_zoom(min_lon, max_lon, min_lat, max_lat, width_px, height_px)
    x0f, x1f = _lon_to_x(min_lon, z), _lon_to_x(max_lon, z)
    y0f, y1f = _lat_to_y(max_lat, z), _lat_to_y(min_lat, z)
    tx0, tx1 = int(math.floor(x0f)), int(math.ceil(x1f)) - 1
    ty0, ty1 = int(math.floor(y0f)), int(math.ceil(y1f)) - 1
    n_tx = max(1, tx1 - tx0 + 1)
    n_ty = max(1, ty1 - ty0 + 1)
    if n_tx * n_ty > MAX_TILES:
        scale = math.sqrt(MAX_TILES / (n_tx * n_ty))
        mid_x = (tx0 + tx1) / 2
        mid_y = (ty0 + ty1) / 2
        half_x = max(1, int((n_tx * scale) / 2))
        half_y = max(1, int((n_ty * scale) / 2))
        tx0, tx1 = int(mid_x - half_x), int(mid_x + half_x)
        ty0, ty1 = int(mid_y - half_y), int(mid_y + half_y)
        n_tx = tx1 - tx0 + 1
        n_ty = ty1 - ty0 + 1
        # Keep geographic projection aligned with the shrunk tile window.
        x0f = max(x0f, float(tx0))
        x1f = min(x1f, float(tx1 + 1))
        y0f = max(y0f, float(ty0))
        y1f = min(y1f, float(ty1 + 1))

    mosaic = Image.new("RGB", (n_tx * TILE_SIZE, n_ty * TILE_SIZE), (230, 233, 238))
    tiles_ok = 0
    jobs = [(ix, iy, tx, ty) for ix, tx in enumerate(range(tx0, tx1 + 1)) for iy, ty in enumerate(range(ty0, ty1 + 1))]

    def _one(job: tuple[int, int, int, int]) -> tuple[int, int, Image.Image | None]:
        ix, iy, tx, ty = job
        n = 2**z
        try:
            tile = _fetch_tile(z, tx % n, max(0, min(n - 1, ty))) if allow_network else None
        except Exception:  # noqa: BLE001
            tile = None
        return ix, iy, tile

    if allow_network and jobs:
        with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
            futs = [pool.submit(_one, j) for j in jobs]
            for fut in as_completed(futs):
                try:
                    ix, iy, tile = fut.result()
                except Exception:  # noqa: BLE001
                    continue
                if tile is not None:
                    mosaic.paste(tile, (ix * TILE_SIZE, iy * TILE_SIZE))
                    tiles_ok += 1

    # Round crop edges — truncating with int() left 1 px pale gutters that read as seams.
    left = max(0, int(round((x0f - tx0) * TILE_SIZE)))
    top = max(0, int(round((y0f - ty0) * TILE_SIZE)))
    right = min(mosaic.width, int(round((x1f - tx0) * TILE_SIZE)))
    bottom = min(mosaic.height, int(round((y1f - ty0) * TILE_SIZE)))
    right = max(left + 8, right)
    bottom = max(top + 8, bottom)
    cropped = mosaic.crop((left, top, right, bottom))
    if cropped.size != (width_px, height_px):
        # Two-step resize: BOX downsample then slight BILINEAR polish — less edge ringing.
        cropped = cropped.resize((width_px, height_px), Image.Resampling.BOX)
    view = cropped
    draw = ImageDraw.Draw(view)

    def project(lat: float, lon: float) -> tuple[float, float]:
        x = (_lon_to_x(lon, z) - x0f) / max(x1f - x0f, 1e-9) * width_px
        y = (_lat_to_y(lat, z) - y0f) / max(y1f - y0f, 1e-9) * height_px
        return x, y

    for mode, path in paths:
        xy = [project(lat, lon) for lat, lon in path]
        if len(xy) < 2:
            continue
        outer, inner = COLOR_CAR if mode == "car" else COLOR_WALK
        draw.line(xy, fill=outer, width=5 if mode == "car" else 4)
        draw.line(xy, fill=inner, width=2)

    if trip.hotel and trip.hotel.lat is not None and trip.hotel.lon is not None:
        hx, hy = project(float(trip.hotel.lat), float(trip.hotel.lon))
        r = 8
        draw.ellipse((hx - r, hy - r, hx + r, hy + r), fill=(194, 239, 158), outline=(14, 23, 77), width=2)

    n = 0
    for day in trip.days:
        for s in day.stops:
            n += 1
            x, y = project(s.lat, s.lon)
            r = 10
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(14, 23, 77), outline=(255, 255, 255), width=2)
            label = str(n)
            font = _map_caption_font(11)
            try:
                tw = draw.textlength(label, font=font)
            except Exception:  # noqa: BLE001
                tw = 6
            draw.text((x - tw / 2, y - 6), label, fill=(255, 255, 255), font=font)

    draw.rectangle((0, height_px - 22, width_px, height_px), fill=(255, 255, 255))
    font = _map_caption_font(12)
    # Latin-only in-image caption — Cyrillic lives in the ReportLab PDF caption.
    note = ATTRIBUTION if tiles_ok else f"{ATTRIBUTION} (no tiles)"
    if not paths:
        note = f"{note} · no verified OSRM geometry"
    elif any(m == "car" for m, _ in paths) and any(m == "walk" for m, _ in paths):
        note = f"{note} · blue: walk · dark: car"
    draw.text((8, height_px - 17), note, fill=(92, 97, 107), font=font)

    buf = io.BytesIO()
    view.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def verified_polyline_point_count(trip: Trip) -> int:
    return sum(len(p) for _m, p in _collect_route_paths(trip))
