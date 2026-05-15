from io import BytesIO
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from utils.profile_template import (
    AvatarSource,
    Box,
    DESKTOP_SIZE,
    fit_font,
    fmt_number,
    load_avatar_image,
    load_font,
    load_symbol_font,
    rounded_rect,
    save_png_buffer,
    text_size,
)


TECNICA_SIZE = DESKTOP_SIZE

TECH_BG = (5, 9, 8)
TECH_BG_DEEP = (2, 5, 4)
TECH_PANEL = (8, 18, 15, 224)
TECH_CARD = (10, 24, 20, 212)
TECH_CARD_SOFT = (12, 30, 24, 188)
TECH_BORDER = (75, 180, 125, 170)
TECH_BORDER_SOFT = (58, 116, 88, 128)
TECH_TEXT = (241, 248, 243)
TECH_MUTED = (173, 198, 181)
TECH_DIM = (103, 139, 116)
TECH_GREEN = (80, 224, 144)
TECH_GREEN_SOFT = (43, 180, 111)
TECH_GREEN_DARK = (18, 100, 69)
TECH_BAR_BG = (20, 35, 29, 240)

TECH_FONT = {
    "h1": 58,
    "points": 72,
    "name": 50,
    "race": 26,
    "panel": 30,
    "section": 24,
    "value": 36,
    "body": 24,
    "label": 21,
    "small": 17,
}


def _safe_text(value: Any, fallback: str = "--") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _fit_text(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: Any,
    max_width: int,
    size: int,
    fill: Tuple[int, int, int] = TECH_TEXT,
    min_size: int = 12,
    bold: bool = False,
    display: bool = False,
    anchor: Optional[str] = None,
) -> None:
    font, value = fit_font(draw, text, max_width, size, min_size, bold, display)
    draw.text(xy, value, font=font, fill=fill, anchor=anchor)


def _line(
    draw: ImageDraw.ImageDraw,
    coords: Tuple[int, int, int, int],
    fill: Tuple[int, int, int, int] = TECH_BORDER_SOFT,
    width: int = 1,
) -> None:
    draw.line(coords, fill=fill, width=width)


def _draw_glow(image: Image.Image, box: Box, color: Tuple[int, int, int], blur: int = 28) -> None:
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse(box, fill=color + (52,))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(blur)))


def _draw_background(image: Image.Image) -> None:
    width, height = image.size
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, height), fill=TECH_BG)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(0, height, 74):
        odraw.line((0, y + 80, width, y - 40), fill=(32, 90, 63, 22), width=1)
    for x in range(0, width, 118):
        odraw.line((x, 0, x + 180, height), fill=(12, 58, 39, 16), width=1)
    for offset in range(-700, 900, 140):
        odraw.line((offset, height, offset + 900, 0), fill=(40, 130, 85, 13), width=4)
    image.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(0.4)))

    _draw_glow(image, (1140, -220, 1930, 520), TECH_GREEN, 64)
    _draw_glow(image, (-260, 610, 570, 1330), TECH_GREEN_DARK, 72)


@lru_cache(maxsize=1)
def _background_image(size: Tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, TECH_BG + (255,))
    _draw_background(image)
    return image


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    box: Box,
    value: Any,
    total: Any,
    color: Tuple[int, int, int] = TECH_GREEN,
) -> None:
    radius = max(2, (box[3] - box[1]) // 2)
    rounded_rect(draw, box, radius=radius, fill=TECH_BAR_BG, outline=(46, 72, 58, 210))
    try:
        total_float = float(total)
        ratio = 0.0 if total_float <= 0 else max(0.0, min(1.0, float(value) / total_float))
    except (TypeError, ValueError):
        ratio = 0.0
    fill_width = int((box[2] - box[0]) * ratio)
    if fill_width > 0:
        rounded_rect(
            draw,
            (box[0], box[1], box[0] + max(radius * 2, fill_width), box[3]),
            radius=radius,
            fill=color + (255,),
            outline=None,
        )


def _draw_sword_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int = 48, mirrored: bool = False) -> None:
    direction = -1 if mirrored else 1
    blade_width = max(3, size // 10)
    x0 = cx - direction * int(size * 0.34)
    y0 = cy + int(size * 0.34)
    x1 = cx + direction * int(size * 0.30)
    y1 = cy - int(size * 0.30)
    tip = (cx + direction * int(size * 0.43), cy - int(size * 0.43))
    guard_cx = cx - direction * int(size * 0.20)
    guard_cy = cy + int(size * 0.20)

    draw.line((x0, y0, x1, y1), fill=TECH_GREEN, width=blade_width)
    draw.polygon(
        [
            tip,
            (x1 - direction * int(size * 0.08), y1 + int(size * 0.02)),
            (x1 + direction * int(size * 0.02), y1 + int(size * 0.08)),
        ],
        fill=TECH_GREEN,
    )
    draw.line(
        (
            guard_cx - direction * int(size * 0.17),
            guard_cy - int(size * 0.04),
            guard_cx + direction * int(size * 0.13),
            guard_cy + int(size * 0.16),
        ),
        fill=TECH_TEXT,
        width=max(2, size // 13),
    )
    pommel = max(3, size // 11)
    draw.ellipse((x0 - pommel, y0 - pommel, x0 + pommel, y0 + pommel), fill=TECH_GREEN)


def _draw_energy_mark(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int = 44) -> None:
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(24, 112, 73), outline=TECH_GREEN, width=2)
    draw.ellipse((cx - radius + 9, cy - radius + 9, cx + radius - 9, cy + radius - 9), outline=(148, 255, 197), width=1)
    _draw_sword_icon(draw, cx - 4, cy + 1, max(30, int(radius * 1.04)))
    _draw_sword_icon(draw, cx + 4, cy + 1, max(30, int(radius * 1.04)), mirrored=True)
    draw.ellipse((cx - 9, cy - 9, cx + 9, cy + 9), fill=TECH_GREEN, outline=TECH_TEXT, width=1)


def _draw_reiatsu_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int = 24) -> None:
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=TECH_TEXT, width=2)
    draw.ellipse((cx - radius + 8, cy - radius + 8, cx + radius - 8, cy + radius - 8), outline=TECH_GREEN, width=2)
    draw.polygon(
        [
            (cx, cy - radius + 5),
            (cx + radius - 7, cy),
            (cx, cy + radius - 5),
            (cx - radius + 7, cy),
        ],
        outline=TECH_GREEN,
    )


def _draw_usage_glyph(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int = 30) -> None:
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(18, 76, 51), outline=TECH_GREEN, width=2)
    draw.ellipse((cx - radius + 8, cy - radius + 8, cx + radius - 8, cy + radius - 8), outline=(126, 247, 181), width=1)
    cuts = [
        (-13, 12, 13, -13, 5),
        (-21, 8, -2, -11, 4),
        (3, 17, 20, 0, 4),
    ]
    for x0, y0, x1, y1, width in cuts:
        draw.line((cx + x0, cy + y0, cx + x1, cy + y1), fill=TECH_GREEN, width=width)
    draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=TECH_TEXT)


def _draw_stat_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, label: str) -> None:
    draw.ellipse((cx - 24, cy - 24, cx + 24, cy + 24), outline=TECH_TEXT, width=2)
    draw.text((cx, cy + 1), label[:1].upper(), font=load_font(20, bold=True), fill=TECH_TEXT, anchor="mm")


def _draw_panel_title(draw: ImageDraw.ImageDraw, x: int, y: int, title: str, icon: str = "blade") -> None:
    if icon == "bars":
        for index, height in enumerate((30, 48, 24, 38)):
            bx = x + index * 11
            draw.rectangle((bx, y + 34 - height, bx + 6, y + 34), fill=TECH_GREEN)
    elif icon == "target":
        draw.ellipse((x, y - 4, x + 42, y + 38), outline=TECH_GREEN, width=4)
        draw.ellipse((x + 12, y + 8, x + 30, y + 26), outline=TECH_GREEN, width=3)
        draw.line((x + 21, y - 10, x + 21, y + 44), fill=TECH_GREEN, width=2)
        draw.line((x - 6, y + 17, x + 48, y + 17), fill=TECH_GREEN, width=2)
    elif icon == "spark":
        points = [(x + 21, y - 6), (x + 28, y + 12), (x + 46, y + 18), (x + 28, y + 25), (x + 21, y + 43), (x + 14, y + 25), (x - 4, y + 18), (x + 14, y + 12)]
        draw.polygon(points, fill=TECH_GREEN)
    elif icon == "status":
        draw.arc((x + 2, y - 4, x + 42, y + 36), 35, 325, fill=TECH_GREEN, width=4)
        draw.line((x + 22, y + 17, x + 36, y + 5), fill=TECH_GREEN, width=4)
        draw.ellipse((x + 18, y + 13, x + 26, y + 21), fill=TECH_TEXT)
    else:
        _draw_sword_icon(draw, x + 25, y + 18, 42)
    draw.text((x + 64, y), title, font=load_font(TECH_FONT["panel"], bold=True), fill=TECH_TEXT)


def _draw_mini_metric(
    draw: ImageDraw.ImageDraw,
    box: Box,
    label: str,
    value: Any,
    suffix: str = "",
) -> None:
    rounded_rect(draw, box, radius=6, fill=TECH_CARD_SOFT, outline=(44, 84, 62, 150))
    x0, y0, x1, _ = box
    _fit_text(draw, (x0 + 24, y0 + 14), label, x1 - x0 - 48, TECH_FONT["label"] - 2, fill=TECH_MUTED)

    value_text = fmt_number(value)
    value_size = TECH_FONT["value"] - 6
    font, value_text = fit_font(draw, value_text, 92, value_size, 20, bold=True)
    value_y = y0 + 43
    draw.text((x0 + 24, value_y), value_text, font=font, fill=TECH_GREEN)
    value_width = text_size(draw, value_text, font)[0]
    if suffix:
        _fit_text(
            draw,
            (x0 + 38 + value_width, value_y + 22),
            suffix,
            max(90, x1 - x0 - value_width - 60),
            TECH_FONT["body"] - 4,
            fill=TECH_TEXT,
            bold=True,
            anchor="lm",
        )


def _draw_usage_stat(draw: ImageDraw.ImageDraw, box: Box, uses: Any) -> None:
    x0, y0, x1, y1 = box
    rounded_rect(draw, box, radius=8, fill=(8, 28, 21, 126), outline=(74, 178, 124, 120), width=1)
    _draw_usage_glyph(draw, x0 + 58, y0 + (y1 - y0) // 2, 31)
    draw.text((x0 + 112, y0 + 18), "TÉCNICAS", font=load_font(TECH_FONT["label"]), fill=TECH_MUTED)
    draw.text((x0 + 112, y0 + 44), "USADAS", font=load_font(TECH_FONT["label"]), fill=TECH_TEXT)
    _fit_text(
        draw,
        (x1 - 58, y0 + (y1 - y0) // 2 + 7),
        fmt_number(uses),
        118,
        TECH_FONT["points"] - 10,
        fill=TECH_GREEN,
        bold=True,
        display=True,
        anchor="mm",
    )


def _draw_metric_row(
    draw: ImageDraw.ImageDraw,
    label: str,
    value: Any,
    y: int,
    x0: int,
    x1: int,
    value_width: int = 220,
) -> None:
    draw.text((x0, y), label, font=load_font(TECH_FONT["label"]), fill=TECH_MUTED)
    _fit_text(draw, (x1, y - 2), value, value_width, TECH_FONT["section"] + 6, fill=TECH_GREEN, bold=True, anchor="ra")


def _draw_number_pair(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    current: Any,
    total: Any,
    max_width: int,
    size: int,
) -> None:
    current_text = fmt_number(current)
    total_text = f" / {fmt_number(total)}"
    full_text = current_text + total_text
    font, _ = fit_font(draw, full_text, max_width, size, 18, bold=True)
    draw.text(xy, current_text, font=font, fill=TECH_GREEN)
    current_width = text_size(draw, current_text, font)[0]
    draw.text((xy[0] + current_width + 10, xy[1]), total_text, font=font, fill=TECH_TEXT)


def _paste_avatar_panel(image: Image.Image, source: AvatarSource, box: Box) -> None:
    x0, y0, x1, y1 = box
    avatar = load_avatar_image(source, x1 - x0, y1 - y0)
    avatar = ImageEnhance.Color(avatar).enhance(0.72)
    avatar = ImageEnhance.Contrast(avatar).enhance(1.16)
    tint = Image.new("RGBA", avatar.size, (12, 74, 45, 82))
    avatar = Image.alpha_composite(avatar, tint)

    shade = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shade)
    for i in range(avatar.height):
        alpha = int(118 * (i / max(1, avatar.height)))
        sdraw.line((0, i, avatar.width, i), fill=(0, 0, 0, alpha))
    avatar = Image.alpha_composite(avatar, shade)
    image.paste(avatar, (x0, y0), avatar)


def normalize_tecnica_data(tecnica_data: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(tecnica_data or {})
    data["title"] = _safe_text(data.get("title"), "SISTEMA DE TÉCNICAS")
    data["subtitle"] = _safe_text(data.get("subtitle"), "技術システム")
    data["name"] = _safe_text(data.get("name", data.get("nome")), "ARASHI")
    data["race"] = _safe_text(data.get("race", data.get("raca")), "SHINIGAMI")
    data["spirit_level"] = _safe_text(data.get("spirit_level", data.get("nivel")), "--")
    data["potential"] = _safe_text(data.get("potential", data.get("potencial_nome")), "Nenhum")
    data["reiatsu"] = data.get("reiatsu", 0)
    data["reiatsu_max"] = data.get("reiatsu_max", data.get("reiatsu_cap", 1))
    data["reiatsu_cap"] = data.get("reiatsu_cap", 1)
    data["cooldown"] = data.get("cooldown", 0)
    data["uses"] = data.get("uses", 0)
    data["official_count"] = data.get("official_count", 0)
    data["created_count"] = data.get("created_count", 0)
    data["buffed_count"] = data.get("buffed_count", 0)
    data["active_buffs"] = data.get("active_buffs", 0)
    data["active_turns"] = data.get("active_turns", 0)
    data["last_tecnica_name"] = _safe_text(data.get("last_tecnica_name"), "Nenhuma")
    data["last_tecnica_type"] = _safe_text(data.get("last_tecnica_type"), "Sem registro")
    data["attributes"] = data.get("attributes") or {}
    return data


def draw_header(draw: ImageDraw.ImageDraw, data: Dict[str, Any], size: Tuple[int, int]) -> None:
    width, _ = size
    rounded_rect(draw, (18, 16, width - 18, 1008), radius=14, fill=None, outline=TECH_BORDER, width=2)
    _draw_energy_mark(draw, 102, 84, 43)
    _fit_text(draw, (178, 42), data.get("title"), 650, TECH_FONT["h1"], bold=True, display=True)
    draw.text((180, 108), data.get("subtitle"), font=load_symbol_font(30), fill=TECH_GREEN)

    _draw_usage_stat(draw, (1248, 34, width - 58, 132), data.get("uses", 0))
    _line(draw, (178, 154, width - 48, 154), fill=(48, 92, 66, 170))


def draw_character_panel(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    avatar_source: AvatarSource,
) -> None:
    x0, y0, x1, y1 = 42, 174, 508, 982
    rounded_rect(draw, (x0, y0, x1, y1), radius=7, fill=TECH_PANEL, outline=TECH_BORDER, width=1)

    avatar_bottom = 650
    _paste_avatar_panel(image, avatar_source or data.get("avatar_source"), (x0 + 1, y0 + 1, x1 - 1, avatar_bottom))

    name_y = 548
    _fit_text(draw, (60, name_y), str(data.get("name")).upper(), 390, TECH_FONT["name"], bold=True, display=True)
    _fit_text(draw, (60, name_y + 58), str(data.get("race")).upper(), 360, TECH_FONT["race"], fill=TECH_GREEN, bold=True)
    _line(draw, (60, 642, x1 - 26, 642), fill=(50, 91, 66, 160))

    rows = [
        ("NÍVEL ESPIRITUAL", data.get("spirit_level"), "N"),
        ("RAÇA", data.get("race"), "R"),
        ("POTENCIAL", data.get("potential"), "P"),
    ]
    y = 681
    row_gap = 74
    for index, (label, value, icon) in enumerate(rows):
        _draw_stat_icon(draw, 90, y + 10, icon)
        draw.text((138, y - 14), label, font=load_font(TECH_FONT["label"]), fill=TECH_MUTED)
        _fit_text(draw, (138, y + 15), value, 300, TECH_FONT["body"], bold=True)
        if index < len(rows) - 1:
            _line(draw, (60, y + 56, x1 - 26, y + 56), fill=(50, 91, 66, 138))
        y += row_gap

    status_y = 890
    _draw_reiatsu_icon(draw, 90, status_y + 10, 24)
    draw.text((138, status_y - 10), "REIATSU", font=load_font(TECH_FONT["body"]), fill=TECH_MUTED)
    _draw_number_pair(draw, (138, status_y + 22), data.get("reiatsu", 0), data.get("reiatsu_max", 1), 312, TECH_FONT["section"] + 2)
    _draw_progress_bar(draw, (64, y1 - 24, x1 - 26, y1 - 8), data.get("reiatsu", 0), data.get("reiatsu_max", 1))


def draw_status_panel(draw: ImageDraw.ImageDraw, data: Dict[str, Any]) -> None:
    _draw_panel_title(draw, 562, 207, "ESTADO", "status")
    rounded_rect(draw, (552, 264, 1740, 434), radius=8, fill=TECH_CARD, outline=TECH_BORDER_SOFT)
    _draw_mini_metric(
        draw,
        (594, 302, 900, 390),
        "BUFFS ATIVOS",
        data.get("active_buffs", 0),
        "técnica(s)",
    )
    _draw_mini_metric(
        draw,
        (936, 302, 1288, 390),
        "DURAÇÃO RESTANTE",
        data.get("active_turns", 0),
        "turno(s)",
    )
    _draw_mini_metric(
        draw,
        (1324, 302, 1698, 390),
        "COOLDOWN",
        data.get("cooldown", 0),
        "turno(s)",
    )

    _draw_progress_bar(draw, (594, 416, 1698, 428), data.get("active_turns", 0), max(1, data.get("active_turns", 1)))
    status = "Nenhum buff físico ativo" if not data.get("active_buffs") else "Buff físico temporário em andamento"
    _fit_text(draw, (1146, 401), status, 600, TECH_FONT["small"] - 1, fill=TECH_MUTED, bold=False, anchor="mm")


def draw_attribute_panel(draw: ImageDraw.ImageDraw, data: Dict[str, Any]) -> None:
    rounded_rect(draw, (530, 460, 1135, 760), radius=8, fill=TECH_PANEL, outline=TECH_BORDER_SOFT)
    _draw_panel_title(draw, 562, 494, "ATRIBUTOS FÍSICOS", "bars")
    rounded_rect(draw, (552, 558, 1114, 738), radius=5, fill=TECH_CARD_SOFT, outline=(44, 84, 62, 150))

    labels = [("forca", "FORÇA"), ("velocidade", "VELOCIDADE"), ("resistencia", "RESISTÊNCIA")]
    y = 596
    for index, (key, label) in enumerate(labels):
        attr = data.get("attributes", {}).get(key, {})
        value = fmt_number(attr.get("final", 0))
        base = fmt_number(attr.get("base", 0))
        _draw_metric_row(draw, label, value, y, 594, 1030, 210)
        draw.text((790, y + 4), f"base {base}", font=load_font(TECH_FONT["small"]), fill=TECH_DIM)
        if index < len(labels) - 1:
            _line(draw, (582, y + 36, 1090, y + 36), fill=(45, 82, 62, 150))
        y += 54


def draw_collection_panel(draw: ImageDraw.ImageDraw, data: Dict[str, Any]) -> None:
    rounded_rect(draw, (1154, 460, 1740, 760), radius=8, fill=TECH_PANEL, outline=TECH_BORDER_SOFT)
    _draw_panel_title(draw, 1188, 494, "ARSENAL", "target")
    rounded_rect(draw, (1178, 558, 1720, 738), radius=5, fill=TECH_CARD_SOFT, outline=(44, 84, 62, 150))

    rows = [
        ("OFICIAIS", fmt_number(data.get("official_count", 0))),
        ("CRIADAS", fmt_number(data.get("created_count", 0))),
        ("COM BUFF", fmt_number(data.get("buffed_count", 0))),
    ]
    y = 596
    for index, (label, value) in enumerate(rows):
        _draw_metric_row(draw, label, value, y, 1218, 1590, 260)
        if index < len(rows) - 1:
            _line(draw, (1200, y + 36, 1696, y + 36), fill=(45, 82, 62, 150))
        y += 54


def draw_last_panel(draw: ImageDraw.ImageDraw, data: Dict[str, Any]) -> None:
    rounded_rect(draw, (530, 782, 1740, 982), radius=8, fill=TECH_PANEL, outline=TECH_BORDER_SOFT)
    _draw_panel_title(draw, 562, 824, "ÚLTIMA TÉCNICA USADA", "spark")
    rounded_rect(draw, (552, 876, 1720, 962), radius=6, fill=TECH_CARD_SOFT, outline=(44, 84, 62, 150))

    _draw_energy_mark(draw, 612, 919, 32)
    _fit_text(draw, (676, 910), data.get("last_tecnica_name"), 900, TECH_FONT["value"] - 2, bold=True, anchor="lm")
    kind = _safe_text(data.get("last_tecnica_type"), "Sem registro")
    if not kind.startswith("(") and kind != "Sem registro":
        kind = f"({kind})"
    _fit_text(draw, (676, 944), kind, 900, TECH_FONT["section"] + 1, fill=TECH_MUTED, bold=False, anchor="lm")


def render_tecnica_card(
    tecnica_data: Dict[str, Any],
    avatar_source: AvatarSource = None,
    size: Tuple[int, int] = TECNICA_SIZE,
) -> Image.Image:
    data = normalize_tecnica_data(tecnica_data)
    image = _background_image(size).copy()
    draw = ImageDraw.Draw(image)

    draw_header(draw, data, size)
    draw_character_panel(image, draw, data, avatar_source)
    draw_status_panel(draw, data)
    draw_attribute_panel(draw, data)
    draw_collection_panel(draw, data)
    draw_last_panel(draw, data)
    return image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=105, threshold=3))


def create_tecnica_card(tecnica_data: Dict[str, Any], avatar_source: AvatarSource = None) -> BytesIO:
    image = render_tecnica_card(tecnica_data, avatar_source=avatar_source)
    return save_png_buffer(image)


TECNICA_EXAMPLE = {
    "title": "SISTEMA DE TÉCNICAS",
    "subtitle": "技術システム",
    "name": "ARASHI",
    "race": "SHINIGAMI",
    "spirit_level": "Grande: Grau Baixo",
    "potential": "Shikai",
    "reiatsu": 16500,
    "reiatsu_max": 16500,
    "reiatsu_cap": 30000,
    "cooldown": 0,
    "uses": 4,
    "official_count": 8,
    "created_count": 2,
    "buffed_count": 5,
    "active_buffs": 1,
    "active_turns": 2,
    "last_tecnica_name": "Shunpo",
    "last_tecnica_type": "Velocidade +20%",
    "attributes": {
        "forca": {"base": 100, "final": 120},
        "velocidade": {"base": 90, "final": 135},
        "resistencia": {"base": 80, "final": 92},
    },
}


if __name__ == "__main__":
    preview = render_tecnica_card(TECNICA_EXAMPLE)
    preview.convert("RGB").save("tecnica_preview.png", quality=95)
