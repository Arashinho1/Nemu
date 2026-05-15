from io import BytesIO
from functools import lru_cache
import math
from typing import Any, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from utils.profile_template import (
    AvatarSource,
    Box,
    DESKTOP_SIZE,
    fmt_number,
    fit_font,
    load_avatar_image,
    load_font,
    load_symbol_font,
    rounded_rect,
    save_png_buffer,
    text_size,
    wrap_text,
)


KIDO_SIZE = DESKTOP_SIZE

KIDO_BG = (4, 4, 13)
KIDO_BG_DEEP = (1, 2, 8)
KIDO_PANEL = (8, 9, 22, 224)
KIDO_CARD = (10, 11, 25, 212)
KIDO_CARD_SOFT = (12, 13, 30, 188)
KIDO_BORDER = (125, 95, 178, 170)
KIDO_BORDER_SOFT = (82, 74, 116, 128)
KIDO_TEXT = (243, 242, 250)
KIDO_MUTED = (177, 175, 194)
KIDO_DIM = (109, 105, 134)
KIDO_PURPLE = (172, 112, 255)
KIDO_PURPLE_SOFT = (129, 80, 220)
KIDO_PURPLE_DARK = (70, 42, 132)
KIDO_BAR_BG = (22, 22, 38, 240)

KIDO_FONT = {
    "h1": 58,
    "brand": 48,
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
    fill: Tuple[int, int, int] = KIDO_TEXT,
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
    fill: Tuple[int, int, int, int] = KIDO_BORDER_SOFT,
    width: int = 1,
) -> None:
    draw.line(coords, fill=fill, width=width)


def _draw_glow(image: Image.Image, box: Box, color: Tuple[int, int, int], blur: int = 28) -> None:
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse(box, fill=color + (54,))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(blur)))


def _draw_kido_background(image: Image.Image) -> None:
    width, height = image.size
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, height), fill=KIDO_BG)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(0, height, 78):
        odraw.line((0, y, width, y + 150), fill=(58, 42, 102, 26), width=1)
    for x in range(0, width, 112):
        odraw.line((x, 0, x + 260, height), fill=(26, 18, 54, 18), width=1)
    for r in range(180, 980, 42):
        alpha = max(7, 42 - r // 34)
        odraw.ellipse((width // 2 - r, height // 2 - r, width // 2 + r, height // 2 + r), outline=(0, 0, 0, alpha), width=22)
    image.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(0.4)))

    _draw_glow(image, (1180, -210, 1910, 520), KIDO_PURPLE, 62)
    _draw_glow(image, (-210, 580, 540, 1320), KIDO_PURPLE_DARK, 70)


@lru_cache(maxsize=1)
def _kido_background_image(size: Tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, KIDO_BG + (255,))
    _draw_kido_background(image)
    return image


def _draw_kido_progress_bar(
    draw: ImageDraw.ImageDraw,
    box: Box,
    value: Any,
    total: Any,
    color: Tuple[int, int, int] = KIDO_PURPLE,
) -> None:
    radius = max(2, (box[3] - box[1]) // 2)
    rounded_rect(draw, box, radius=radius, fill=KIDO_BAR_BG, outline=(48, 44, 72, 210))
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


def _draw_kido_flame(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    scale: float = 1.0,
    color: Tuple[int, int, int] = KIDO_PURPLE,
) -> None:
    raw = [(0, 62), (15, 34), (24, 54), (37, 4), (53, 54), (70, 28), (65, 74), (36, 100)]
    pts = [(int(x + px * scale), int(y + py * scale)) for px, py in raw]
    draw.polygon(pts, fill=color)
    inner = [(int(x + 22 * scale + px * scale * 0.42), int(y + 38 * scale + py * scale * 0.42)) for px, py in raw]
    draw.polygon(inner, fill=KIDO_BG)


def _draw_energy_mark(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int = 44) -> None:
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(103, 63, 194), outline=KIDO_PURPLE, width=2)
    nodes = [
        (cx - 17, cy - 5),
        (cx + 12, cy - 19),
        (cx + 18, cy + 18),
        (cx - 20, cy + 20),
    ]
    for index, point in enumerate(nodes):
        next_point = nodes[(index + 1) % len(nodes)]
        draw.line(point + next_point, fill=KIDO_BG_DEEP, width=6)
    for nx, ny in nodes:
        draw.ellipse((nx - 9, ny - 9, nx + 9, ny + 9), fill=KIDO_BG_DEEP)


def _hex_points(cx: int, cy: int, radius: int) -> list[Tuple[float, float]]:
    return [
        (
            cx + math.cos(math.radians(60 * i - 90)) * radius,
            cy + math.sin(math.radians(60 * i - 90)) * radius,
        )
        for i in range(6)
    ]


def _draw_kido_hex_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int = 60, symbol: str = "封") -> None:
    pts = _hex_points(cx, cy, radius)
    draw.line(pts + [pts[0]], fill=KIDO_PURPLE, width=4)
    inner = _hex_points(cx, cy, radius - 12)
    draw.line(inner + [inner[0]], fill=(102, 72, 165), width=1)
    draw.text((cx, cy + 1), symbol, font=load_symbol_font(max(28, int(radius * 0.92))), fill=KIDO_PURPLE, anchor="mm")


def _draw_stat_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, label: str) -> None:
    draw.ellipse((cx - 24, cy - 24, cx + 24, cy + 24), outline=KIDO_TEXT, width=2)
    draw.text((cx, cy + 1), label[:1].upper(), font=load_font(20, bold=True), fill=KIDO_TEXT, anchor="mm")


def _draw_panel_title(draw: ImageDraw.ImageDraw, x: int, y: int, title: str, icon: str = "flame") -> None:
    if icon == "bars":
        for index, height in enumerate((34, 48, 25, 39)):
            bx = x + index * 11
            draw.rectangle((bx, y + 34 - height, bx + 6, y + 34), fill=KIDO_PURPLE)
    elif icon == "pie":
        draw.pieslice((x, y - 2, x + 42, y + 40), start=0, end=270, fill=KIDO_PURPLE)
        draw.line((x + 21, y + 19, x + 21, y - 1), fill=KIDO_BG, width=3)
        draw.line((x + 21, y + 19, x + 43, y + 19), fill=KIDO_BG, width=3)
    elif icon == "spiral":
        for radius in range(18, 4, -4):
            draw.arc((x + 20 - radius, y + 18 - radius, x + 20 + radius, y + 18 + radius), 25, 330, fill=KIDO_PURPLE, width=4)
    else:
        _draw_kido_flame(draw, x, y - 18, 0.42)
    draw.text((x + 64, y), title, font=load_font(KIDO_FONT["panel"], bold=True), fill=KIDO_TEXT)


def _draw_metric_row(
    draw: ImageDraw.ImageDraw,
    label: str,
    value: Any,
    y: int,
    x0: int,
    x1: int,
    value_width: int = 220,
) -> None:
    draw.text((x0, y), label, font=load_font(KIDO_FONT["label"]), fill=KIDO_MUTED)
    _fit_text(draw, (x1, y - 2), value, value_width, KIDO_FONT["section"] + 6, fill=KIDO_PURPLE, bold=True, anchor="ra")


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
    draw.text(xy, current_text, font=font, fill=KIDO_PURPLE)
    current_width = text_size(draw, current_text, font)[0]
    draw.text((xy[0] + current_width + 10, xy[1]), total_text, font=font, fill=KIDO_TEXT)


def _paste_kido_avatar_panel(image: Image.Image, source: AvatarSource, box: Box) -> None:
    x0, y0, x1, y1 = box
    avatar = load_avatar_image(source, x1 - x0, y1 - y0)
    avatar = ImageEnhance.Color(avatar).enhance(0.62)
    avatar = ImageEnhance.Contrast(avatar).enhance(1.18)
    tint = Image.new("RGBA", avatar.size, (48, 20, 94, 78))
    avatar = Image.alpha_composite(avatar, tint)

    shade = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shade)
    for i in range(avatar.height):
        alpha = int(118 * (i / max(1, avatar.height)))
        sdraw.line((0, i, avatar.width, i), fill=(0, 0, 0, alpha))
    avatar = Image.alpha_composite(avatar, shade)
    image.paste(avatar, (x0, y0), avatar)


def normalize_kido_data(kido_data: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(kido_data or {})
    data["title"] = _safe_text(data.get("title"), "SISTEMA DE KIDŌ")
    data["subtitle"] = _safe_text(data.get("subtitle"), "鬼道システム")
    data["name"] = _safe_text(data.get("name", data.get("nome")), "ARASHI")
    data["race"] = _safe_text(data.get("race", data.get("raca")), "SHINIGAMI")
    data["spirit_level"] = _safe_text(data.get("spirit_level", data.get("nivel")), "--")
    data["potential"] = _safe_text(data.get("potential", data.get("potencial_nome")), "Nenhum")
    data["reiatsu"] = data.get("reiatsu", 0)
    data["reiatsu_max"] = data.get("reiatsu_max", data.get("reiatsu_cap", 1))
    data["reiatsu_cap"] = data.get("reiatsu_cap", 1)
    data["reiryoku"] = data.get("reiryoku", data.get("reiryoku_atual", 0))
    data["reiryoku_max"] = data.get("reiryoku_max", 1)
    data["cooldown"] = data.get("cooldown", 0)
    data["tier"] = _safe_text(data.get("tier"), "1 / 6")
    data["access"] = _safe_text(data.get("access"), "#1 ao #15")
    data["skill_bonus"] = _safe_text(data.get("skill_bonus"), "+0%")
    data["uses"] = data.get("uses", data.get("usos_total", 0))
    data["total_cost"] = data.get("total_cost", data.get("gasto_total", 0))
    data["power_total"] = data.get("power_total", data.get("poder_total", 0))
    data["last_power"] = data.get("last_power", data.get("ultimo_poder", 0))
    data["last_kido_name"] = _safe_text(data.get("last_kido_name"), "Nenhum")
    data["last_kido_type"] = _safe_text(data.get("last_kido_type"), "Sem registro")
    return data


def draw_kido_header(draw: ImageDraw.ImageDraw, data: Dict[str, Any], size: Tuple[int, int]) -> None:
    width, _ = size
    rounded_rect(draw, (18, 16, width - 18, 1008), radius=14, fill=None, outline=KIDO_BORDER, width=2)
    _draw_energy_mark(draw, 102, 84, 43)
    _fit_text(draw, (178, 42), data.get("title"), 620, KIDO_FONT["h1"], bold=True, display=True)
    draw.text((180, 108), data.get("subtitle"), font=load_symbol_font(30), fill=KIDO_PURPLE)

    divider_x = width - 488
    metric_center = width - 318
    _line(draw, (divider_x, 56, divider_x, 122), fill=KIDO_BORDER_SOFT)
    _fit_text(draw, (metric_center, 60), "ÚLTIMA POTÊNCIA", 300, KIDO_FONT["body"], fill=KIDO_TEXT, anchor="mm")
    _fit_text(
        draw,
        (metric_center, 108),
        fmt_number(data.get("last_power", 0)),
        310,
        KIDO_FONT["points"] - 8,
        fill=KIDO_PURPLE,
        bold=True,
        display=True,
        anchor="mm",
    )
    _draw_kido_flame(draw, width - 145, 38, 0.64, KIDO_PURPLE)
    _line(draw, (178, 154, width - 48, 154), fill=(61, 54, 88, 170))


def draw_kido_character_panel(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    data: Dict[str, Any],
    avatar_source: AvatarSource,
) -> None:
    # Painel esquerdo refatorado para impedir sobreposição entre Potencial e Reiatsu.
    x0, y0, x1, y1 = 42, 174, 508, 982
    rounded_rect(draw, (x0, y0, x1, y1), radius=7, fill=KIDO_PANEL, outline=KIDO_BORDER, width=1)

    avatar_bottom = 650
    _paste_kido_avatar_panel(image, avatar_source or data.get("avatar_source"), (x0 + 1, y0 + 1, x1 - 1, avatar_bottom))

    name_y = 548
    _fit_text(draw, (60, name_y), str(data.get("name")).upper(), 390, KIDO_FONT["name"], bold=True, display=True)
    _fit_text(draw, (60, name_y + 58), str(data.get("race")).upper(), 360, KIDO_FONT["race"], fill=KIDO_PURPLE, bold=True)
    _line(draw, (60, 642, x1 - 26, 642), fill=(57, 50, 82, 160))

    rows = [
        ("NÍVEL ESPIRITUAL", data.get("spirit_level"), "N"),
        ("RAÇA", data.get("race"), "R"),
        ("POTENCIAL", data.get("potential"), "P"),
    ]

    # Altura compacta por linha: mantém as três infos no painel sem invadir o bloco de Reiatsu.
    y = 681
    row_gap = 74
    for index, (label, value, icon) in enumerate(rows):
        _draw_stat_icon(draw, 90, y + 10, icon)
        draw.text((138, y - 14), label, font=load_font(KIDO_FONT["label"]), fill=KIDO_MUTED)
        _fit_text(draw, (138, y + 15), value, 300, KIDO_FONT["body"], bold=True)
        if index < len(rows) - 1:
            _line(draw, (60, y + 56, x1 - 26, y + 56), fill=(57, 50, 82, 138))
        y += row_gap

    # Bloco Reiatsu isolado, com ícone menor e texto alinhado.
    status_y = 890
    _draw_kido_flame(draw, 76, status_y - 6, 0.34, KIDO_PURPLE)
    draw.text((138, status_y - 10), "REIATSU", font=load_font(KIDO_FONT["body"]), fill=KIDO_MUTED)
    _draw_number_pair(
        draw,
        (138, status_y + 22),
        data.get("reiatsu", 0),
        data.get("reiatsu_max", 1),
        312,
        KIDO_FONT["section"] + 2,
    )
    _draw_kido_progress_bar(draw, (64, y1 - 24, x1 - 26, y1 - 8), data.get("reiatsu", 0), data.get("reiatsu_max", 1))


def draw_kido_energy_panel(draw: ImageDraw.ImageDraw, data: Dict[str, Any]) -> None:
    _draw_panel_title(draw, 562, 207, "ENERGIA")
    rounded_rect(draw, (552, 264, 1740, 434), radius=8, fill=KIDO_CARD, outline=KIDO_BORDER_SOFT)
    draw.text((594, 308), "REIRYOKU", font=load_font(KIDO_FONT["label"]), fill=KIDO_MUTED)
    _draw_number_pair(
        draw,
        (594, 344),
        data.get("reiryoku", 0),
        data.get("reiryoku_max", 1),
        720,
        KIDO_FONT["value"],
    )
    _draw_kido_progress_bar(draw, (594, 400, 1426, 419), data.get("reiryoku", 0), data.get("reiryoku_max", 1))

    draw.text((1650, 308), "COOLDOWN", font=load_font(KIDO_FONT["label"]), fill=KIDO_MUTED, anchor="ra")
    cooldown_text = f"{fmt_number(data.get('cooldown', 0))} turno(s)"
    _fit_text(draw, (1685, 355), cooldown_text, 260, KIDO_FONT["section"] + 7, fill=KIDO_PURPLE, bold=True, anchor="ra")


def draw_kido_domain_panel(draw: ImageDraw.ImageDraw, data: Dict[str, Any]) -> None:
    rounded_rect(draw, (530, 460, 1135, 760), radius=8, fill=KIDO_PANEL, outline=KIDO_BORDER_SOFT)
    _draw_panel_title(draw, 562, 494, "DOMÍNIO", "bars")
    rounded_rect(draw, (552, 558, 1114, 738), radius=5, fill=KIDO_CARD_SOFT, outline=(54, 48, 75, 150))

    rows = [
        ("TIER", data.get("tier")),
        ("ACESSO", data.get("access")),
        ("BÔNUS DE PERÍCIA", data.get("skill_bonus")),
    ]
    y = 596
    for index, (label, value) in enumerate(rows):
        _draw_metric_row(draw, label, value, y, 594, 1030, 210)
        if index < len(rows) - 1:
            _line(draw, (582, y + 36, 1090, y + 36), fill=(55, 50, 76, 150))
        y += 54


def draw_kido_usage_panel(draw: ImageDraw.ImageDraw, data: Dict[str, Any]) -> None:
    rounded_rect(draw, (1154, 460, 1740, 760), radius=8, fill=KIDO_PANEL, outline=KIDO_BORDER_SOFT)
    _draw_panel_title(draw, 1188, 494, "USO CONTABILIZADO", "pie")
    rounded_rect(draw, (1178, 558, 1720, 738), radius=5, fill=KIDO_CARD_SOFT, outline=(54, 48, 75, 150))

    rows = [
        ("USOS", fmt_number(data.get("uses", 0))),
        ("GASTO TOTAL", fmt_number(data.get("total_cost", 0))),
        ("POTÊNCIA TOTAL", fmt_number(data.get("power_total", 0))),
    ]
    y = 596
    for index, (label, value) in enumerate(rows):
        _draw_metric_row(draw, label, value, y, 1218, 1590, 260)
        if index < len(rows) - 1:
            _line(draw, (1200, y + 36, 1696, y + 36), fill=(55, 50, 76, 150))
        y += 54


def draw_kido_last_spell_panel(draw: ImageDraw.ImageDraw, data: Dict[str, Any]) -> None:
    rounded_rect(draw, (530, 782, 1740, 982), radius=8, fill=KIDO_PANEL, outline=KIDO_BORDER_SOFT)
    _draw_panel_title(draw, 562, 824, "ÚLTIMO KIDŌ USADO", "spiral")
    rounded_rect(draw, (552, 876, 1720, 962), radius=6, fill=KIDO_CARD_SOFT, outline=(54, 48, 75, 150))
    _draw_kido_hex_icon(draw, 612, 919, 32)

    _fit_text(draw, (676, 910), data.get("last_kido_name"), 900, KIDO_FONT["value"] - 2, bold=True, anchor="lm")
    kind = _safe_text(data.get("last_kido_type"), "Sem registro")
    if not kind.startswith("(") and kind != "Sem registro":
        kind = f"({kind})"
    _fit_text(draw, (676, 944), kind, 900, KIDO_FONT["section"] + 1, fill=KIDO_MUTED, bold=False, anchor="lm")


def render_kido_card(
    kido_data: Dict[str, Any],
    avatar_source: AvatarSource = None,
    size: Tuple[int, int] = KIDO_SIZE,
) -> Image.Image:
    data = normalize_kido_data(kido_data)
    image = _kido_background_image(size).copy()
    draw = ImageDraw.Draw(image)

    draw_kido_header(draw, data, size)
    draw_kido_character_panel(image, draw, data, avatar_source)
    draw_kido_energy_panel(draw, data)
    draw_kido_domain_panel(draw, data)
    draw_kido_usage_panel(draw, data)
    draw_kido_last_spell_panel(draw, data)
    return image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=105, threshold=3))


def create_kido_card(kido_data: Dict[str, Any], avatar_source: AvatarSource = None) -> BytesIO:
    image = render_kido_card(kido_data, avatar_source=avatar_source)
    return save_png_buffer(image)


KIDO_EXAMPLE = {
    "title": "SISTEMA DE KIDŌ",
    "subtitle": "鬼道システム",
    "name": "ARASHI",
    "race": "SHINIGAMI",
    "spirit_level": "Grande: Grau Baixo",
    "potential": "Nenhum",
    "reiatsu": 16500,
    "reiatsu_max": 16500,
    "reiatsu_cap": 30000,
    "reiryoku": 99010,
    "reiryoku_max": 100010,
    "cooldown": 0,
    "tier": "1 / 6",
    "access": "#1 ao #15",
    "skill_bonus": "+0%",
    "uses": 2,
    "total_cost": 200,
    "power_total": 100010,
    "last_power": 739932,
    "last_kido_name": "Sai",
    "last_kido_type": "Bakudō #1",
}


if __name__ == "__main__":
    preview = render_kido_card(KIDO_EXAMPLE)
    preview.convert("RGB").save("kido_preview.png", quality=95)
