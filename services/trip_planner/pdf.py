"""О!Маршрут PDF — personal guidebook (dynamic for any city / 1–7 days)."""
from __future__ import annotations

import io
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .map_render import render_trip_map_png, verified_polyline_point_count
from .models import DayPlan, Stop, TravelSegment, Trip
from .photos import commons_attribution, directions_link, fetch_image_bytes, maps_link, resolve_photo_ref
from .text_shape import contains_arabic, pdf_safe

# Brand palette
NAVY = colors.HexColor("#0e174d")
NAVY_SOFT = colors.HexColor("#131e5d")
INK = colors.HexColor("#15171c")
MUTED = colors.HexColor("#5c616b")
LINE = colors.HexColor("#d8dbe3")
CARD = colors.HexColor("#f4f6f9")
SAGE = colors.HexColor("#e7f0ea")
SAGE_INK = colors.HexColor("#1f4d3a")
WHITE = colors.white
BRAND_GREEN = colors.HexColor("#c2ef9e")

CATEGORY_RU: dict[str, str] = {
    "museum": "Музей",
    "beach": "Пляж",
    "restaurant": "Ресторан",
    "bar": "Бар",
    "cafe": "Кафе",
    "park": "Парк",
    "attraction": "Достопримечательность",
    "viewpoint": "Смотровая",
    "religious": "Храм",
    "shopping": "Шопинг",
}

MODE_RU = {"walk": "пешком", "car": "на машине", "transit": "транспортом"}

_CHAT_SUMMARY = re.compile(
    r"Оставил|Оставила|Не нашёл|Убрал|Добавил|Заменил|Учтено|Транспорт:|Изменения:|не нашёл",
    re.I,
)

_IMG_CACHE: dict[str, bytes | None] = {}


class _Hairline(Flowable):
    def __init__(self, width: float, color: colors.Color = LINE, thickness: float = 0.6):
        super().__init__()
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = 4

    def draw(self) -> None:
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 2, self.width, 2)


def _register_fonts() -> tuple[str, str]:
    """Return (regular, bold) with Cyrillic + Arabic coverage when possible."""
    pairs = [
        # Segoe UI covers Cyrillic + Arabic on Windows
        (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf")),
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
        ),
    ]
    for regular, bold in pairs:
        if regular.exists() and bold.exists():
            try:
                pdfmetrics.registerFont(TTFont("TripCyr", str(regular)))
                pdfmetrics.registerFont(TTFont("TripCyr-Bold", str(bold)))
                return "TripCyr", "TripCyr-Bold"
            except Exception:  # noqa: BLE001
                continue
    for regular, _ in pairs:
        if regular.exists():
            try:
                pdfmetrics.registerFont(TTFont("TripCyr", str(regular)))
                return "TripCyr", "TripCyr"
            except Exception:  # noqa: BLE001
                continue
    return "Helvetica", "Helvetica-Bold"


def _esc(text: str) -> str:
    """Shape (Arabic RTL) + escape for ReportLab Paragraph XML."""
    return pdf_safe(text)


def _days_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "дня"
    return "дней"


def _places_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "место"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "места"
    return "мест"


def _short_address(addr: str) -> str:
    if not addr:
        return ""
    noise = {
        "france",
        "france métropolitaine",
        "île-de-france",
        "türkiye",
        "turkey",
        "magyarország",
        "hungary",
        "russia",
        "россия",
        "marmara bölgesi",
        "budapest",
        "istanbul",
        "paris",
        "united arab emirates",
        "uae",
    }
    parts = [p.strip() for p in addr.split(",") if p.strip()]
    cleaned: list[str] = []
    for p in parts:
        low = p.lower()
        if low in noise:
            continue
        if "bölgesi" in low or "métropolitaine" in low or ("arrondissement" in low and len(cleaned) >= 2):
            continue
        if re.fullmatch(r"\d{4,6}", p):
            continue
        cleaned.append(p)
    return ", ".join(cleaned[:3])


def _clean_description(desc: str, name: str) -> str:
    if not desc:
        return ""
    d = desc.strip()
    if re.search(r"OSM\s*/", d, re.I):
        return ""
    if re.match(rf"^{re.escape(name)}\s*[—\-–]\s*", d, re.I):
        rest = re.sub(rf"^{re.escape(name)}\s*[—\-–]\s*", "", d, flags=re.I).strip()
        if not rest or rest.lower() in CATEGORY_RU or "/" in rest:
            return ""
        return rest
    if d.lower() == name.lower():
        return ""
    return d


def _format_travel(seg: TravelSegment) -> str:
    if getattr(seg, "verified", True) is False:
        return "маршрут не подтверждён"
    km = f"{seg.distanceMeters / 1000:.1f}".replace(".", ",")
    mins = max(1, round(seg.durationSeconds / 60))
    return f"{km} км · {mins} мин {MODE_RU.get(seg.mode, seg.mode)}"


# Nominative → dative for common RU city names in «маршрут по …».
_CITY_DATIVE: dict[str, str] = {
    "Казань": "Казани",
    "Москва": "Москве",
    "Анталья": "Анталье",
    "Стамбул": "Стамбулу",
    "Сочи": "Сочи",
    "Дубай": "Дубаю",
    "Санкт-Петербург": "Санкт-Петербургу",
}


def _route_city_phrase(city: str) -> str:
    """Avoid broken «Маршрут по Казань» — use dative or neutral dash."""
    c = (city or "").strip() or "поездка"
    dative = _CITY_DATIVE.get(c)
    if dative:
        return f"Маршрут по {dative}"
    # Latin / already-inflected / unknown: no forced «по» + nominative.
    if re.search(r"[А-Яа-яЁё]$", c) and c[-1] in "аяь":
        # Soft heuristic: Казань→Казани, Москва→Москве
        if c.endswith("ь"):
            return f"Маршрут по {c[:-1]}и"
        if c.endswith("а"):
            return f"Маршрут по {c[:-1]}е"
        if c.endswith("я"):
            return f"Маршрут по {c[:-1]}е"
    return f"Маршрут — {c}"


def _human_summary(trip: Trip) -> str:
    n_days = len(trip.days) or max(1, trip.intent.days)
    n_stops = sum(len(d.stops) for d in trip.days)
    city = trip.destination.name or trip.intent.destination or "поездка"
    base = f"{_route_city_phrase(city)}: {n_days} {_days_word(n_days)}, {n_stops} {_places_word(n_stops)}."
    raw = (trip.summary or "").strip()
    if raw and not _CHAT_SUMMARY.search(raw) and "из открытых данных" not in raw.lower():
        if len(raw) < 180 and raw != base and "Маршрут по " not in raw:
            return raw
        # Fix legacy stored summaries with broken «по Казань».
        fixed = re.sub(
            r"Маршрут по Казань\b",
            "Маршрут по Казани",
            raw,
        )
        if fixed != raw:
            return fixed
        if len(raw) < 180 and raw != base:
            return raw
    return base


def _styles(font: str, bold: str) -> dict[str, ParagraphStyle]:
    return {
        "brand": ParagraphStyle(
            "PdfBrand", fontName=bold, fontSize=12, leading=15, textColor=SAGE_INK
        ),
        "coverTitle": ParagraphStyle(
            "PdfCoverTitle", fontName=bold, fontSize=28, leading=32, textColor=NAVY, spaceAfter=4
        ),
        "title": ParagraphStyle(
            "PdfTitle", fontName=bold, fontSize=20, leading=24, textColor=NAVY, spaceAfter=2
        ),
        "subtitle": ParagraphStyle(
            "PdfSub", fontName=font, fontSize=11, leading=15, textColor=MUTED
        ),
        "body": ParagraphStyle(
            "PdfBody", fontName=font, fontSize=10, leading=14, textColor=INK
        ),
        "day": ParagraphStyle(
            "PdfDay", fontName=bold, fontSize=15, leading=19, textColor=NAVY
        ),
        "dayMeta": ParagraphStyle(
            "PdfDayMeta", fontName=font, fontSize=9, leading=12, textColor=MUTED
        ),
        "time": ParagraphStyle(
            "PdfTime", fontName=bold, fontSize=11, leading=14, textColor=NAVY, alignment=TA_CENTER
        ),
        "stopName": ParagraphStyle(
            "PdfStopName", fontName=bold, fontSize=12, leading=15, textColor=INK
        ),
        "stopBody": ParagraphStyle(
            "PdfStopBody", fontName=font, fontSize=9, leading=12, textColor=MUTED
        ),
        "chip": ParagraphStyle(
            "PdfChip", fontName=font, fontSize=8.5, leading=11, textColor=SAGE_INK
        ),
        "leg": ParagraphStyle(
            "PdfLeg", fontName=font, fontSize=9, leading=12, textColor=MUTED, alignment=TA_LEFT
        ),
        "footer": ParagraphStyle(
            "PdfFooter", fontName=font, fontSize=8, leading=11, textColor=MUTED, alignment=TA_CENTER
        ),
        "link": ParagraphStyle(
            "PdfLink", fontName=font, fontSize=9, leading=12, textColor=NAVY_SOFT, alignment=TA_LEFT
        ),
        "mapCap": ParagraphStyle(
            "PdfMapCap", fontName=font, fontSize=8.5, leading=11, textColor=MUTED, alignment=TA_CENTER
        ),
    }


def _fetch_image_bytes(url: str, timeout: float = 5.0) -> bytes | None:
    if url in _IMG_CACHE:
        return _IMG_CACHE[url]
    data = fetch_image_bytes(url, timeout=timeout)
    _IMG_CACHE[url] = data
    return data


def _stop_image(stop: Stop, max_w: float, max_h: float) -> tuple[Flowable | None, str | None]:
    """Return (image flowable, resolved https url used) — url for attribution only if image loaded."""
    url = stop.photoUrl
    if not url or not str(url).startswith("http"):
        wd = getattr(stop, "wikidataId", None)
        url = resolve_photo_ref(stop.photoUrl, wd, width=960)
    if not url:
        return None, None
    data = _fetch_image_bytes(url)
    if not data:
        return None, None
    try:
        img = Image(io.BytesIO(data))
        img.hAlign = "LEFT"
        iw, ih = float(img.imageWidth), float(img.imageHeight)
        if iw <= 0 or ih <= 0:
            return None, None
        scale = min(max_w / iw, max_h / ih)
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        return img, url
    except Exception:  # noqa: BLE001
        return None, None


def _photo_credit(url: str | None, styles: dict[str, ParagraphStyle]) -> Paragraph | None:
    """Credit only when a real image URL was successfully used."""
    if not url or not str(url).startswith("http"):
        return None
    if "wikimedia" not in url and "wikipedia" not in url:
        return Paragraph("Фото: источник OSM (https)", styles["mapCap"])
    # Short timeout — missing credit is better than a multi-second stall per photo.
    attr = commons_attribution(url, timeout=0.8)
    if not attr:
        attr = "Wikimedia Commons"
    return Paragraph(_esc(f"Фото: {attr}"), styles["mapCap"])


def _qr_flowable(data: str, size: float = 28 * mm) -> Flowable | None:
    """QR with ≥4-module quiet zone; size is the printed square including quiet zone."""
    try:
        import qrcode
    except ImportError:
        return None
    try:
        # Quiet zone must be ≥4 modules for reliable screen + print scans.
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        pil = qr.make_image(fill_color="#0e174d", back_color="white")
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        # Floor size so dense payloads stay scannable after A4 print.
        draw = max(float(size), 18 * mm)
        img = Image(buf, width=draw, height=draw)
        return img
    except Exception:  # noqa: BLE001
        return None


def _link_label(url: str, label: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    """Clickable short label — never dump a wrapping raw URL into the layout."""
    return Paragraph(f'<link href="{_esc(url)}">{_esc(label)}</link>', styles["link"])


def _overview_map(trip: Trip, width: float, height: float) -> Flowable | None:
    """Raster map with OSM basemap + verified OSRM road geometry (never fake straight roads)."""
    has_stops = any(d.stops for d in trip.days)
    if not has_stops:
        return None
    png = render_trip_map_png(
        trip,
        # Lower raster DPI — tiles + route stay sharp enough in A4; cuts build time.
        width_px=max(640, int(width * 1.55)),
        height_px=max(360, int(height * 1.55)),
        allow_network=True,
    )
    if not png:
        return None
    try:
        img = Image(io.BytesIO(png), width=width, height=height)
        img.hAlign = "CENTER"
        return img
    except Exception:  # noqa: BLE001
        return None


def _trip_transport_label(trip: Trip) -> str:
    modes = {s.mode for d in trip.days for s in d.segments if getattr(s, "verified", True)}
    if modes == {"walk"}:
        return "пешком"
    if modes == {"car"}:
        return "на машине"
    if modes == {"walk", "car"}:
        return "пешком + авто"
    return MODE_RU.get(trip.intent.transportPreference, trip.intent.transportPreference)


def _meta_chips(trip: Trip, font: str) -> Table:
    n_days = len(trip.days) or trip.intent.days
    n_stops = sum(len(d.stops) for d in trip.days)
    start = trip.intent.startTime or "10:00"
    end = trip.intent.returnBy or trip.intent.endTime or "20:00"
    transport = _trip_transport_label(trip)
    chips = [
        f"{n_days} {_days_word(n_days)}",
        f"{n_stops} {_places_word(n_stops)}",
        # Requested planning window — actual stop times are listed per day below.
        f"окно {start}–{end}",
        str(transport),
    ]
    if trip.hotel and trip.hotel.name:
        chips.append(f"база: {_esc(trip.hotel.name)}")
    cells = [
        [
            Paragraph(
                _esc(c),
                ParagraphStyle(
                    f"chip{i}",
                    fontName=font,
                    fontSize=9,
                    leading=12,
                    textColor=NAVY_SOFT,
                    alignment=TA_CENTER,
                ),
            )
            for i, c in enumerate(chips)
        ]
    ]
    tbl = Table(cells, colWidths=[None] * len(chips))
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SAGE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, WHITE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return tbl


def _cover(trip: Trip, styles: dict, content_w: float, font: str, bold: str) -> list:
    blocks: list = []
    city = trip.destination.name or trip.intent.destination or "Поездка"
    country = (trip.destination.country or "").strip()

    brand_row = Table(
        [[
            Paragraph("О!Хочу", ParagraphStyle("b1", fontName=bold, fontSize=16, textColor=NAVY)),
            Paragraph("О!Маршрут · персональный путеводитель", styles["subtitle"]),
        ]],
        colWidths=[40 * mm, content_w - 40 * mm],
    )
    brand_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    blocks.append(brand_row)
    blocks.append(Spacer(1, 10))

    # Cover photo from first stop with a real photo
    cover_img = None
    cover_url = None
    for day in trip.days:
        for stop in day.stops:
            cover_img, cover_url = _stop_image(stop, content_w, 55 * mm)
            if cover_img:
                break
        if cover_img:
            break
    if cover_img:
        blocks.append(cover_img)
        credit = _photo_credit(cover_url, styles)
        if credit:
            blocks.append(Spacer(1, 2))
            blocks.append(credit)
        blocks.append(Spacer(1, 8))
    else:
        # Branded wash bar
        bar = Table([[""]], colWidths=[content_w], rowHeights=[18 * mm])
        bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SAGE), ("BOX", (0, 0), (-1, -1), 0, SAGE)]))
        blocks.append(bar)
        blocks.append(Spacer(1, 8))

    blocks.append(Paragraph(_esc(city), styles["coverTitle"]))
    if country:
        blocks.append(Paragraph(_esc(country), styles["subtitle"]))
    blocks.append(Spacer(1, 4))
    blocks.append(Paragraph(_esc(_human_summary(trip)), styles["body"]))
    blocks.append(Spacer(1, 8))
    blocks.append(_meta_chips(trip, font))

    if trip.hotel and trip.hotel.name:
        blocks.append(Spacer(1, 8))
        blocks.append(
            Paragraph(
                f"Точка старта: <b>{_esc(trip.hotel.name)}</b>"
                + (f" · {_esc(trip.hotel.city or '')}" if trip.hotel.city else ""),
                styles["body"],
            )
        )

    incomplete = [d.dayNumber for d in trip.days if getattr(d, "incomplete", False) or not d.stops]
    if incomplete:
        blocks.append(Spacer(1, 6))
        blocks.append(
            Paragraph(
                f"Внимание: день(и) {', '.join(map(str, incomplete))} без подтверждённых остановок.",
                styles["dayMeta"],
            )
        )

    blocks.append(Spacer(1, 10))
    blocks.append(
        Paragraph(
            "Места и координаты — из открытых картографических данных (OSM/Wikidata). "
            "Фотографии — Wikimedia Commons по привязке к объекту. "
            "Неподтверждённые переезды отмечены явно.",
            styles["footer"],
        )
    )
    return blocks


def _stop_card(
    index: int,
    stop: Stop,
    styles: dict[str, ParagraphStyle],
    content_w: float,
    bold: str,
) -> Table:
    cat = CATEGORY_RU.get(stop.category, stop.category or "Место")
    addr = _short_address(stop.address)
    desc = _clean_description(stop.description or "", stop.name)
    bits = [cat, f"{stop.durationMinutes} мин"]
    if stop.rating is not None:
        bits.append(f"рейтинг {stop.rating:g}")
    meta_line = " · ".join(bits)

    photo_mm = 26 * mm
    photo, photo_url = _stop_image(stop, photo_mm, photo_mm)
    if photo is None:
        # Branded placeholder — never invent stock photos
        initial = (stop.name or cat or "•").strip()[:1].upper() or "•"
        # Short label — avoid truncated «Достопримечате» in the placeholder.
        ph_cat = {
            "Достопримечательность": "место",
            "attraction": "место",
        }.get(cat, cat if len(cat) <= 10 else cat[:9] + "…")
        ph = Table(
            [
                [
                    Paragraph(
                        f"<font size='14'><b>{_esc(initial)}</b></font><br/><font size='6.5'>{_esc(ph_cat)}</font>",
                        ParagraphStyle(
                            "ph",
                            fontName=bold,
                            fontSize=8,
                            leading=11,
                            textColor=NAVY,
                            alignment=TA_CENTER,
                        ),
                    )
                ]
            ],
            colWidths=[photo_mm],
            rowHeights=[photo_mm],
        )
        ph.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SAGE),
                    ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        photo_cell = ph
    else:
        photo_cell = photo

    # Point marker — not turn-by-turn navigation.
    osm = maps_link(stop.lat, stop.lon, stop.name)
    link_p = _link_label(osm, "Точка на карте", styles)
    qr = _qr_flowable(osm, size=20 * mm)

    if contains_arabic(stop.name):
        # Avoid mixed LTR/RTL glitches: index after the shaped Arabic name.
        name_p = Paragraph(f"{_esc(stop.name)} · {index}", styles["stopName"])
    else:
        name_p = Paragraph(f"{index}. {_esc(stop.name)}", styles["stopName"])
    meta_p = Paragraph(_esc(meta_line), styles["chip"])
    detail_bits: list[str] = []
    if desc:
        detail_bits.append(_esc(desc))
    if addr:
        detail_bits.append(_esc(addr))
    detail_p = Paragraph("<br/>".join(detail_bits), styles["stopBody"]) if detail_bits else Spacer(1, 0)
    time_p = Paragraph(_esc(stop.startTime or "—"), styles["time"])

    mid_w = content_w - 28 * mm - 22 * mm - 6 * mm
    credit = _photo_credit(photo_url, styles) if photo is not None else None
    mid_rows = [[name_p], [meta_p], [time_p]]
    if detail_bits:
        mid_rows.append([detail_p])
    mid_rows.append([link_p])
    if credit is not None:
        mid_rows.append([credit])
    mid = Table(mid_rows, colWidths=[mid_w])
    mid.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    right = qr if qr else Spacer(20 * mm, 20 * mm)
    inner = Table([[photo_cell, mid, right]], colWidths=[28 * mm, mid_w, 22 * mm])
    inner.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 1),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    card = Table([[inner]], colWidths=[content_w])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CARD),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return card


def _leg_row(
    label: str,
    styles: dict[str, ParagraphStyle],
    content_w: float,
    *,
    route_url: str | None = None,
) -> Table:
    """Travel chip between stops. Optional QR opens real OSM directions (not a pin)."""
    text = Paragraph(f"↓  {_esc(label)}", styles["leg"])
    if route_url:
        qr = _qr_flowable(route_url, size=16 * mm)
        link = _link_label(route_url, "Маршрут на карте", styles)
        mid = Table([[text], [link]], colWidths=[content_w - 30 * mm])
        mid.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        right = qr if qr else Spacer(18 * mm, 18 * mm)
        tbl = Table(
            [[Spacer(10 * mm, 1), mid, right]],
            colWidths=[10 * mm, content_w - 30 * mm, 20 * mm],
        )
    else:
        tbl = Table([[Spacer(14 * mm, 1), text]], colWidths=[14 * mm, content_w - 14 * mm])
    tbl.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return tbl


def _day_block(
    day: DayPlan,
    styles: dict[str, ParagraphStyle],
    content_w: float,
    bold: str,
    hotel_ll: tuple[float, float] | None = None,
) -> list:
    blocks: list = []
    verified_segs = [s for s in day.segments if getattr(s, "verified", True)]
    route_ok = getattr(day.route, "verified", True)
    if getattr(day, "incomplete", False) or not day.stops:
        totals = "неполный результат"
    elif not route_ok or any(not getattr(s, "verified", True) for s in day.segments):
        totals = "часть переездов не подтверждена"
    else:
        km = (
            day.route.distanceMeters / 1000
            if day.route.distanceMeters
            else sum(s.distanceMeters for s in verified_segs) / 1000
        )
        mins = max(
            0,
            round((day.route.durationSeconds or sum(s.durationSeconds for s in verified_segs)) / 60),
        )
        totals = f"{km:.1f} км в пути · {mins} мин переездов" if km or mins else ""
    first = day.stops[0].startTime if day.stops else ""
    last_end = ""
    if day.stops:
        last = day.stops[-1]
        try:
            h, m = map(int, (last.startTime or "0:0").split(":"))
            total = h * 60 + m + int(last.durationMinutes or 0)
            last_end = f"{total // 60:02d}:{total % 60:02d}"
        except ValueError:
            last_end = ""
    window = f"факт {first}–{last_end}" if first and last_end else (f"факт {first}" if first else "")
    place_bit = f"{len(day.stops)} {_places_word(len(day.stops))}" if day.stops else "без остановок"
    header_bits = [x for x in [window, place_bit, totals] if x]

    head = Table(
        [
            [
                Paragraph(f"День {day.dayNumber}", styles["day"]),
                Paragraph(" · ".join(header_bits), styles["dayMeta"]),
            ]
        ],
        colWidths=[28 * mm, content_w - 28 * mm],
    )
    head.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    blocks.append(head)
    blocks.append(_Hairline(content_w, LINE, 0.8))
    blocks.append(Spacer(1, 6))

    if day.summary and not _CHAT_SUMMARY.search(day.summary):
        blocks.append(Paragraph(_esc(day.summary), styles["dayMeta"]))
        blocks.append(Spacer(1, 4))

    if not day.stops:
        blocks.append(Paragraph("В этом дне нет подтверждённых остановок.", styles["dayMeta"]))
        return blocks

    def _seg_route_url(seg: TravelSegment, origin: tuple[float, float] | None, dest: tuple[float, float] | None) -> str | None:
        if not origin or not dest or not getattr(seg, "verified", True):
            return None
        return directions_link(origin[0], origin[1], dest[0], dest[1], mode=seg.mode or "walk")

    for i, stop in enumerate(day.stops, start=1):
        # Group incoming travel + stop so the last place is never orphaned alone.
        chunk: list = []
        if i == 1:
            hotel_leg = next(
                (s for s in day.segments if s.fromStopId == "hotel" and s.toStopId == stop.id),
                None,
            )
            if hotel_leg:
                url = _seg_route_url(hotel_leg, hotel_ll, (stop.lat, stop.lon))
                chunk.append(
                    _leg_row(
                        f"От отеля · {_format_travel(hotel_leg)}",
                        styles,
                        content_w,
                        route_url=url,
                    )
                )
        else:
            prev = day.stops[i - 2]
            seg_in = next((s for s in day.segments if s.fromStopId == prev.id and s.toStopId == stop.id), None)
            if seg_in:
                url = _seg_route_url(seg_in, (prev.lat, prev.lon), (stop.lat, stop.lon))
                chunk.append(_leg_row(_format_travel(seg_in), styles, content_w, route_url=url))

        chunk.append(_stop_card(i, stop, styles, content_w, bold))

        if i == len(day.stops):
            seg_home = next((s for s in day.segments if s.fromStopId == stop.id and s.toStopId == "hotel"), None)
            if seg_home:
                url = _seg_route_url(seg_home, (stop.lat, stop.lon), hotel_ll)
                chunk.append(
                    _leg_row(
                        f"Возврат в отель · {_format_travel(seg_home)}",
                        styles,
                        content_w,
                        route_url=url,
                    )
                )

        chunk.append(Spacer(1, 3))
        blocks.append(KeepTogether(chunk))

    return blocks


def build_trip_pdf(trip: Trip, web_link: str | None = None) -> bytes:
    # Best-effort photo enrich for older trips stored without HTTPS thumbs
    try:
        from .photos import enrich_trip_photos

        trip = enrich_trip_photos(trip, timeout_s=4.0)
    except Exception:  # noqa: BLE001
        pass

    font, bold = _register_fonts()
    styles = _styles(font, bold)
    buf = io.BytesIO()
    page_w, _page_h = A4
    left = 14 * mm
    right = 14 * mm
    content_w = page_w - left - right

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"О!Маршрут — {trip.destination.name}",
        author="О!Хочу",
    )

    story: list = []
    story.extend(_cover(trip, styles, content_w, font, bold))
    story.append(PageBreak())

    # Overview map (compact) + QR; keep map short so day stops stay on the same page.
    n_stops = sum(len(d.stops) for d in trip.days)
    map_h = 42 * mm if n_stops <= 4 else (52 * mm if n_stops <= 6 else 64 * mm)
    story.append(Paragraph("Обзор маршрута", styles["title"]))
    story.append(Spacer(1, 2))
    drawing = _overview_map(trip, content_w, map_h)
    if drawing:
        story.append(drawing)
        story.append(Spacer(1, 2))
        geom_n = verified_polyline_point_count(trip)
        if geom_n >= 2:
            map_note = (
                "Карта: OpenStreetMap. "
                f"Линии — подтверждённая геометрия OSRM ({geom_n} точек); "
                "синий — пешком, тёмный — авто. Неподтверждённые переезды не рисуются."
            )
        else:
            map_note = (
                "Карта: OpenStreetMap и остановки. "
                "Подтверждённой геометрии OSRM нет — прямые «дороги» не изображаются."
            )
        story.append(Paragraph(map_note, styles["mapCap"]))
    else:
        story.append(Paragraph("Недостаточно координат для схемы.", styles["dayMeta"]))
    story.append(Spacer(1, 4))

    hotel_ll = None
    if trip.hotel and trip.hotel.lat is not None and trip.hotel.lon is not None:
        hotel_ll = (float(trip.hotel.lat), float(trip.hotel.lon))

    # Main QR: permanent trip link when available; otherwise honest single-leg / pin.
    first_stop = next((s for d in trip.days for s in d.stops), None)
    osm_nav = (
        maps_link(first_stop.lat, first_stop.lon, first_stop.name) if first_stop else None
    )
    first_leg = None
    if first_stop and hotel_ll:
        for day in trip.days:
            first_leg = next(
                (s for s in day.segments if s.fromStopId == "hotel" and s.toStopId == first_stop.id),
                None,
            )
            if first_leg:
                break
    start_route = None
    if first_stop and hotel_ll and first_leg and getattr(first_leg, "verified", True):
        start_route = directions_link(
            hotel_ll[0], hotel_ll[1], first_stop.lat, first_stop.lon, mode=first_leg.mode or "walk"
        )

    demo_link = False
    public_web = None
    if web_link and "127.0.0.1" not in web_link and "localhost" not in web_link:
        if "example" in web_link or "o-hochu.example" in web_link:
            demo_link = True
        else:
            public_web = web_link

    if public_web:
        qr_payload, caption, link_label = public_web, "Весь маршрут онлайн (постоянная ссылка)", "Открыть маршрут"
    elif start_route:
        qr_payload, caption, link_label = (
            start_route,
            "QR: только переезд от отеля до первой точки (не весь маршрут)",
            "Открыть переезд в OSM",
        )
    elif osm_nav:
        qr_payload, caption, link_label = (
            osm_nav,
            "QR: точка старта на карте (не полный маршрут)",
            "Открыть точку в OSM",
        )
    else:
        qr_payload, caption, link_label = None, "", ""

    if qr_payload:
        qr = _qr_flowable(qr_payload, size=26 * mm)
        link_p = _link_label(qr_payload, link_label, styles)
        rows: list = [[Paragraph(caption, styles["body"])], [link_p]]
        if demo_link and web_link:
            rows.append(
                [
                    Paragraph(
                        f"Демо-ссылка (образец, не QR): {_esc(web_link)}",
                        styles["dayMeta"],
                    )
                ]
            )
        right = Table(rows, colWidths=[content_w - 30 * mm])
        if qr:
            story.append(Table([[qr, right]], colWidths=[30 * mm, content_w - 30 * mm]))
        else:
            story.append(right)
        story.append(Spacer(1, 3))
    elif demo_link and web_link:
        story.append(
            Paragraph(f"Демо-ссылка (образец): {_esc(web_link)}", styles["dayMeta"])
        )
        story.append(Spacer(1, 3))

    # Day schedule — skip empty incomplete days to avoid blank pages.
    days_emitted = 0
    for day in trip.days:
        if not day.stops and getattr(day, "incomplete", False):
            continue
        if days_emitted > 0:
            story.append(PageBreak())
        story.extend(_day_block(day, styles, content_w, bold, hotel_ll=hotel_ll))
        days_emitted += 1

    def _footer(canvas, _doc) -> None:  # noqa: ANN001
        canvas.saveState()
        canvas.setFillColor(MUTED)
        canvas.setFont(font, 7)
        canvas.drawCentredString(
            page_w / 2,
            11 * mm,
            "О!Хочу · О!Маршрут · документ сформирован автоматически · проверяйте часы работы на месте",
        )
        canvas.setFont(font, 8)
        canvas.drawCentredString(page_w / 2, 6 * mm, f"О!Маршрут  ·  стр. {_doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
