from io import BytesIO
from functools import lru_cache
import math
from pathlib import Path
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

# =========================================================
# BLEACH ATTRIBUTE PROFILE TEMPLATE — HORIZONTAL / EMBED PNG
# Mantém compatibilidade com create_profile_card(profile_data, avatar_source)
# =========================================================

DESKTOP_SIZE = (1792, 1024)
MOBILE_SIZE = (1080, 1920)

COLOR_BG = (2, 7, 15)
COLOR_PANEL = (5, 11, 23, 228)
COLOR_CARD = (6, 13, 27, 202)
COLOR_CARD_SOFT = (8, 17, 34, 188)
COLOR_BORDER = (43, 58, 80, 210)
COLOR_BORDER_SOFT = (70, 84, 108, 135)
COLOR_TEXT = (245, 247, 252)
COLOR_MUTED = (158, 166, 182)
COLOR_DIM = (86, 95, 112)
COLOR_BLUE = (58, 153, 255)
COLOR_RED = (242, 64, 70)
COLOR_YELLOW = (255, 184, 45)
COLOR_BAR_BG = (31, 40, 58)

ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets"
FONT_ROOT = ASSET_ROOT / "fonts"
SHINIGAMI_BADGE_PATH = ASSET_ROOT / "icons" / "shinigami-badge-seeklogo.png"

FONT_PATHS_DISPLAY = (
    "NotoSansCJKjp-Regular.otf",
    "impact.ttf", "Impact.ttf", "bahnschrift.ttf", "Bahnschrift.ttf",
    "arialbd.ttf", "Arial Bold.ttf", "segoeuib.ttf",
    "DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf", "FreeSansBold.ttf",
)
FONT_PATHS_BOLD = (
    "NotoSansCJKjp-Regular.otf",
    "bahnschrift.ttf", "arialbd.ttf", "segoeuib.ttf", "Arial Bold.ttf",
    "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf",
)
FONT_PATHS_REGULAR = (
    "NotoSansCJKjp-Regular.otf",
    "bahnschrift.ttf", "arial.ttf", "segoeui.ttf", "Arial.ttf",
    "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf",
)
FONT_PATHS_CJK = (
    "NotoSansCJKjp-Regular.otf",
    "NotoSansCJK-Regular.ttc", "NotoSansCJK-Bold.ttc",
    "NotoSansJP-Regular.otf", "NotoSansJP-Bold.otf",
    "DroidSansFallbackFull.ttf", "DroidSansFallback.ttf",
    "C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
)
FONT_SEARCH_DIRS = (
    FONT_ROOT,
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/liberation2"),
    Path("/usr/share/fonts/truetype/freefont"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/opentype/noto"),
    Path("/usr/share/fonts/opentype/noto-cjk"),
    Path("/usr/local/share/fonts"),
)
SYMBOL_FALLBACKS = {
    "属性システム": "ATRIBUTOS",
    "ブリーチ": "BLEACH",
    "力": "F",
    "速": "V",
    "忍": "R",
}

DESKTOP_FONT = {
    "h1": 58, "brand": 58, "points": 82, "name": 46,
    "race": 24, "attr_title": 46, "attr_value": 56,
    "attr_bonus": 42, "body": 21, "label": 18, "small": 16,
}
MOBILE_FONT = {
    "h1": 52, "brand": 42, "points": 72, "name": 48,
    "race": 24, "attr_title": 42, "attr_value": 46,
    "attr_bonus": 34, "body": 22, "label": 18, "small": 15,
}

ATTRIBUTE_COLORS = {
    "forca": COLOR_RED, "força": COLOR_RED, "red": COLOR_RED,
    "velocidade": COLOR_BLUE, "blue": COLOR_BLUE,
    "resistencia": COLOR_YELLOW, "resistência": COLOR_YELLOW, "yellow": COLOR_YELLOW,
}
ATTRIBUTE_DEFAULTS = {
    "forca": ("FORÇA", "AUMENTA O PODER DE ATAQUE.", "力"),
    "força": ("FORÇA", "AUMENTA O PODER DE ATAQUE.", "力"),
    "velocidade": ("VELOCIDADE", "AUMENTA A AGILIDADE E ESQUIVA.", "速"),
    "resistencia": ("RESISTÊNCIA", "AUMENTA A DEFESA E RESILIÊNCIA.", "忍"),
    "resistência": ("RESISTÊNCIA", "AUMENTA A DEFESA E RESILIÊNCIA.", "忍"),
}

AvatarSource = Optional[Union[str, bytes, Image.Image]]
Box = Tuple[int, int, int, int]


def is_mobile_size(size: Tuple[int, int]) -> bool:
    return size[0] <= 1000 or size == MOBILE_SIZE


def fmt_number(value: Any) -> str:
    try:
        number = float(value)
        if math.isinf(number):
            return "∞"
        return f"{int(number):,}".replace(",", ".")
    except (TypeError, ValueError, OverflowError):
        return str(value)


def font_candidates(names: Tuple[Union[str, Path], ...]) -> List[str]:
    candidates: List[str] = []
    seen = set()
    for name in names:
        value = str(name)
        path = Path(value)
        if path.is_absolute() or "/" in value or "\\" in value:
            options = [path]
        else:
            options = [directory / value for directory in FONT_SEARCH_DIRS]
            options.append(path)
        for option in options:
            candidate = str(option)
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)
    return candidates


@lru_cache(maxsize=256)
def load_font(size: int, bold: bool = False, display: bool = False) -> ImageFont.ImageFont:
    names: List[str] = []
    if display:
        names.extend(FONT_PATHS_DISPLAY)
    if bold:
        names.extend(FONT_PATHS_BOLD)
    names.extend(FONT_PATHS_REGULAR)
    for name in font_candidates(tuple(names)):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


@lru_cache(maxsize=64)
def load_symbol_font(size: int) -> ImageFont.ImageFont:
    for name in font_candidates(FONT_PATHS_CJK):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return load_font(size, bold=True, display=True)


@lru_cache(maxsize=1)
def has_symbol_font() -> bool:
    for name in font_candidates(FONT_PATHS_CJK):
        try:
            ImageFont.truetype(name, 12)
            return True
        except OSError:
            continue
    return False


def symbol_text(value: Any) -> str:
    text = str(value)
    if has_symbol_font():
        return text
    return SYMBOL_FALLBACKS.get(text, text)


def text_size(draw: ImageDraw.ImageDraw, text: Any, font: ImageFont.ImageFont) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), str(text), font=font)
    return box[2] - box[0], box[3] - box[1]


def fit_font(draw: ImageDraw.ImageDraw, text: Any, max_width: int, size: int, min_size: int = 10,
             bold: bool = False, display: bool = False) -> Tuple[ImageFont.ImageFont, str]:
    value = str(text)
    for current in range(size, min_size - 1, -1):
        font = load_font(current, bold=bold, display=display)
        if text_size(draw, value, font)[0] <= max_width:
            return font, value
    font = load_font(min_size, bold=bold, display=display)
    ellipsis = "..."
    trimmed = value
    while trimmed and text_size(draw, trimmed + ellipsis, font)[0] > max_width:
        trimmed = trimmed[:-1]
    return font, (trimmed + ellipsis) if trimmed else ellipsis


def draw_fit_text(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: Any, max_width: int, size: int,
                  fill: Tuple[int, int, int] = COLOR_TEXT, min_size: int = 10, bold: bool = False,
                  display: bool = False, anchor: Optional[str] = None) -> None:
    font, value = fit_font(draw, text, max_width, size, min_size, bold, display)
    draw.text(xy, value, font=font, fill=fill, anchor=anchor)


def wrap_text(draw: ImageDraw.ImageDraw, text: Any, font: ImageFont.ImageFont, max_width: int,
              max_lines: Optional[int] = None) -> List[str]:
    lines: List[str] = []
    for raw in str(text or "").splitlines() or [""]:
        current = ""
        for word in raw.split():
            test = f"{current} {word}".strip()
            if not current or text_size(draw, test, font)[0] <= max_width:
                current = test
            else:
                lines.append(current)
                current = word
                if max_lines and len(lines) >= max_lines:
                    return truncate_last_line(draw, lines, font, max_width)
        if current:
            lines.append(current)
            if max_lines and len(lines) >= max_lines:
                return truncate_last_line(draw, lines, font, max_width)
    return lines


def truncate_last_line(draw: ImageDraw.ImageDraw, lines: List[str], font: ImageFont.ImageFont, max_width: int) -> List[str]:
    if not lines:
        return lines
    ellipsis = "..."
    last = lines[-1]
    while last and text_size(draw, last + ellipsis, font)[0] > max_width:
        last = last[:-1]
    lines[-1] = (last + ellipsis) if last else ellipsis
    return lines


def rounded_rect(draw: ImageDraw.ImageDraw, box: Box, radius: int = 8,
                 fill: Optional[Tuple[int, ...]] = None,
                 outline: Optional[Tuple[int, ...]] = COLOR_BORDER,
                 width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def line(draw: ImageDraw.ImageDraw, coords: Tuple[int, int, int, int],
         fill: Tuple[int, ...] = COLOR_BORDER_SOFT, width: int = 1) -> None:
    draw.line(coords, fill=fill, width=width)


def normalize_ratio(value: Any, total: Any) -> float:
    try:
        total_float = float(total)
        if total_float <= 0:
            return 0.0
        return max(0.0, min(1.0, float(value) / total_float))
    except (TypeError, ValueError):
        return 0.0


def reiatsu_display_max(data: Dict[str, Any]) -> Any:
    return data.get("reiatsu_max", data.get("reiatsu_cap", 0))


def cover_image(source: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.fit(source.convert("RGBA"), (width, height), method=Image.Resampling.LANCZOS)


def load_avatar_image(source: AvatarSource, width: int, height: int) -> Image.Image:
    try:
        if isinstance(source, Image.Image):
            image = source.convert("RGBA")
        elif isinstance(source, bytes):
            image = Image.open(BytesIO(source)).convert("RGBA")
        elif isinstance(source, str) and source.startswith(("http://", "https://")):
            with urllib.request.urlopen(source, timeout=8) as response:
                image = Image.open(BytesIO(response.read())).convert("RGBA")
        elif isinstance(source, str) and source:
            image = Image.open(source).convert("RGBA")
        else:
            image = Image.new("RGBA", (width, height), (16, 24, 39, 255))
    except (OSError, urllib.error.URLError, ValueError):
        image = Image.new("RGBA", (width, height), (16, 24, 39, 255))
    return cover_image(image, width, height)


def paste_avatar_panel(image: Image.Image, source: AvatarSource, box: Box) -> None:
    x0, y0, x1, y1 = box
    avatar = load_avatar_image(source, x1 - x0, y1 - y0)
    avatar = ImageEnhance.Color(avatar).enhance(0.42)
    avatar = ImageEnhance.Contrast(avatar).enhance(1.22)
    shade = Image.new("RGBA", avatar.size, (0, 10, 24, 85))
    avatar = Image.alpha_composite(avatar, shade)
    # gradient escuro inferior/esquerdo para leitura
    grad = Image.new("RGBA", avatar.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    h = avatar.size[1]
    for i in range(h):
        a = int(130 * (i / max(1, h)))
        gdraw.line((0, i, avatar.size[0], i), fill=(0, 0, 0, a))
    avatar = Image.alpha_composite(avatar, grad)
    image.paste(avatar, (x0, y0), avatar)


def draw_progress_bar(draw: ImageDraw.ImageDraw, box: Box, value: Any, total: Any,
                      color: Tuple[int, int, int] = COLOR_BLUE) -> None:
    radius = max(2, (box[3] - box[1]) // 2)
    rounded_rect(draw, box, radius=radius, fill=COLOR_BAR_BG + (245,), outline=None)
    ratio = normalize_ratio(value, total)
    fill_width = int((box[2] - box[0]) * ratio)
    if fill_width > 0:
        rounded_rect(draw, (box[0], box[1], box[0] + max(radius * 2, fill_width), box[3]),
                     radius=radius, fill=color + (255,), outline=None)


def draw_background(image: Image.Image) -> None:
    width, height = image.size
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, height), fill=COLOR_BG)
    # Vinheta radial simples
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for r in range(0, max(width, height), 22):
        alpha = int(min(160, r / max(width, height) * 180))
        od.ellipse((width//2-r, height//2-r, width//2+r, height//2+r), outline=(0, 0, 0, alpha), width=20)
    # Brush strokes superiores/inferiores
    for i in range(20):
        od.line((880 + i*12, 78 + i*2, 1520 + i*10, 28 + i*3), fill=(0, 0, 0, 130), width=max(4, 22 - i))
        od.line((1220 + i*10, height - 88 + i*3, width, height - 150 + i*2), fill=(0, 0, 0, 110), width=max(3, 16 - i//2))
    for i in range(18):
        od.line((260 + i*28, 0, 1060 + i*12, 145), fill=(76, 92, 118, max(12, 52-i*2)), width=max(5, 28-i))
    image.alpha_composite(overlay.filter(ImageFilter.GaussianBlur(0.35)))


@lru_cache(maxsize=2)
def background_image(size: Tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, COLOR_BG + (255,))
    draw_background(image)
    return image


def flame_points(x: int, y: int, scale: float) -> List[Tuple[int, int]]:
    raw = [(0, 62), (14, 34), (22, 52), (34, 4), (50, 52), (66, 28), (61, 72), (34, 98)]
    return [(int(x + px * scale), int(y + py * scale)) for px, py in raw]


def draw_flame_mark(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0,
                    color: Tuple[int, int, int] = COLOR_TEXT) -> None:
    draw.polygon(flame_points(x, y, scale), fill=color)
    draw.polygon(flame_points(int(x + 20 * scale), int(y + 36 * scale), scale * 0.42), fill=COLOR_BG)


def draw_header(draw: ImageDraw.ImageDraw, data: Dict[str, Any], size: Tuple[int, int], fonts: Dict[str, int]) -> None:
    width, _ = size
    if not is_mobile_size(size):
        draw_flame_mark(draw, 36, 34, 0.84)
        draw_fit_text(draw, (120, 34), data.get("title", "ATRIBUTOS"), 360, fonts["h1"], bold=True, display=True)
        draw.text((123, 104), symbol_text(data.get("subtitle", "属性システム")), font=load_symbol_font(fonts["body"]), fill=COLOR_BLUE)
        line(draw, (10, 154, width - 28, 154), fill=(32, 45, 66))

        points_label_x = 1120
        points_value_x = 1308
        draw.text((points_label_x, 82), str(data.get("points_label", "PONTOS\nDISPONÍVEIS")), font=load_font(fonts["label"]), fill=COLOR_MUTED, anchor="mm", spacing=6)
        line(draw, (points_label_x + 112, 54, points_label_x + 112, 111), fill=COLOR_BORDER_SOFT)
        draw.text((points_value_x, 80), fmt_number(data.get("points_available", 0)), font=load_font(fonts["points"], bold=True, display=True), fill=COLOR_BLUE, anchor="lm")

        draw_fit_text(draw, (width - 34, 42), data.get("brand", "BLEACH"), 260, fonts["brand"], bold=True, display=True, anchor="ra")
        draw.text((width - 55, 106), symbol_text(data.get("brand_sub", "ブリーチ")), font=load_symbol_font(fonts["body"]), fill=COLOR_BLUE, anchor="ra")
        return

    draw_flame_mark(draw, 38, 36, 0.78)
    draw_fit_text(draw, (122, 42), data.get("title", "ATRIBUTOS"), 360, fonts["h1"], bold=True, display=True)
    draw.text((124, 108), symbol_text(data.get("subtitle", "属性システム")), font=load_symbol_font(fonts["body"]), fill=COLOR_BLUE)

    points_label_x = width - 615
    points_value_x = width - 405
    draw.text((points_label_x, 82), str(data.get("points_label", "PONTOS\nDISPONÍVEIS")), font=load_font(fonts["label"]), fill=COLOR_MUTED, anchor="mm", spacing=7)
    line(draw, (points_label_x + 118, 54, points_label_x + 118, 118), fill=COLOR_BORDER_SOFT)
    draw.text((points_value_x, 84), fmt_number(data.get("points_available", 0)), font=load_font(fonts["points"], bold=True, display=True), fill=COLOR_BLUE, anchor="lm")

    draw_fit_text(draw, (width - 38, 48), data.get("brand", "BLEACH"), 250, fonts["brand"], bold=True, display=True, anchor="ra")
    draw.text((width - 42, 112), symbol_text(data.get("brand_sub", "ブリーチ")), font=load_symbol_font(fonts["body"]), fill=COLOR_BLUE, anchor="ra")
    line(draw, (34, 146, width - 34, 146), fill=(32, 45, 66))


def draw_info_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, label: str, fonts: Dict[str, int]) -> None:
    draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=COLOR_TEXT, width=2)
    draw.text((cx, cy + 1), label[:1].upper(), font=load_font(fonts["label"], bold=True), fill=COLOR_TEXT, anchor="mm")


def draw_image_info_icon(image: Image.Image, draw: ImageDraw.ImageDraw, cx: int, cy: int,
                         asset_path: Path, size: int = 32) -> bool:
    if not asset_path.exists():
        return False
    try:
        icon = Image.open(asset_path).convert("RGBA")
    except OSError:
        return False

    pixels = []
    for r, g, b, a in icon.getdata():
        if a and g > 70 and r < 110 and b < 110 and g > r + 18 and g > b + 18:
            pixels.append((r, g, b, 0))
        else:
            pixels.append((r, g, b, a))
    icon.putdata(pixels)

    if not icon.getbbox():
        return False

    icon = icon.crop(icon.getbbox())
    icon.thumbnail((size - 4, size - 4), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ox = (size - icon.width) // 2
    oy = (size - icon.height) // 2
    canvas.alpha_composite(icon, (ox, oy))

    draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=COLOR_TEXT, width=2)
    image.alpha_composite(canvas, (cx - size // 2, cy - size // 2 + 1))
    return True


def draw_character_panel(image: Image.Image, draw: ImageDraw.ImageDraw, data: Dict[str, Any],
                         avatar_source: AvatarSource, size: Tuple[int, int], fonts: Dict[str, int]) -> None:
    width, _ = size
    if not is_mobile_size(size):
        x0, y0, x1, y1 = 10, 160, 386, 1014
        rounded_rect(draw, (x0, y0, x1, y1), radius=3, fill=COLOR_PANEL, outline=COLOR_BORDER)
        paste_avatar_panel(image, avatar_source or data.get("avatar_source"), (x0 + 1, y0 + 1, x1 - 1, 600))
        draw_fit_text(draw, (46, 513), str(data.get("name", "ARASHI")).upper(), 270, fonts["name"], bold=True, display=True)
        draw_fit_text(draw, (46, 565), str(data.get("race", "SHINIGAMI")).upper(), 260, fonts["race"], fill=COLOR_BLUE, bold=True)

        rows = [
            ("NÍVEL ESPIRITUAL", data.get("spirit_level", "--"), "N"),
            ("RAÇA", data.get("race", "--"), "R"),
            ("POTENCIAL", data.get("potential", "Nenhum"), "P"),
        ]
        y = 650
        for i, (label, value, icon) in enumerate(rows):
            if label == "RAÇA":
                if not draw_image_info_icon(image, draw, 66, y + 2, SHINIGAMI_BADGE_PATH):
                    draw_info_icon(draw, 66, y + 2, icon, fonts)
            else:
                draw_info_icon(draw, 66, y + 2, icon, fonts)
            text_y_offset = 8 if label == "RAÇA" else 0
            draw.text((108, y - 23 + text_y_offset), label, font=load_font(fonts["label"]), fill=COLOR_MUTED)
            draw_fit_text(draw, (108, y + 4 + text_y_offset), value, 230, fonts["body"], bold=True)
            if i < len(rows) - 1:
                line(draw, (34, y + 51, 360, y + 51), fill=(32, 45, 66))
            y += 80

        status_y = 890
        draw_flame_mark(draw, 44, status_y - 22, 0.54, COLOR_BLUE)
        draw.text((106, status_y), str(data.get("reiatsu_label", "REIATSU")), font=load_font(fonts["body"]), fill=COLOR_MUTED)
        reiatsu_max = reiatsu_display_max(data)
        reiatsu_value = f"{fmt_number(data.get('reiatsu', 0))} / {fmt_number(reiatsu_max)}"
        draw_fit_text(draw, (106, status_y + 34), reiatsu_value, 230, fonts["race"], fill=COLOR_TEXT, bold=True)
        draw_progress_bar(draw, (44, status_y + 83, 354, status_y + 96), data.get("reiatsu", 0), reiatsu_max, COLOR_BLUE)
        return

    # Mobile: painel vertical com a mesma leitura do perfil desktop.
    x0, y0, x1, y1 = 38, 166, width - 38, 700
    rounded_rect(draw, (x0, y0, x1, y1), radius=8, fill=COLOR_PANEL, outline=COLOR_BORDER)
    avatar_box = (x0 + 12, y0 + 12, x0 + 420, y1 - 12)
    paste_avatar_panel(image, avatar_source or data.get("avatar_source"), avatar_box)
    draw_fit_text(draw, (x0 + 44, y1 - 110), str(data.get("name", "ARASHI")).upper(), 330, fonts["name"], bold=True, display=True)
    draw_fit_text(draw, (x0 + 44, y1 - 56), str(data.get("race", "SHINIGAMI")).upper(), 315, fonts["race"], fill=COLOR_BLUE, bold=True)

    rows = [
        ("NÍVEL ESPIRITUAL", data.get("spirit_level", "--"), "N"),
        ("RAÇA", data.get("race", "--"), "R"),
        ("POTENCIAL", data.get("potential", "Nenhum"), "P"),
    ]
    info_x = x0 + 500
    y = y0 + 86
    for i, (label, value, icon) in enumerate(rows):
        if label == "RAÇA":
            if not draw_image_info_icon(image, draw, info_x, y + 2, SHINIGAMI_BADGE_PATH):
                draw_info_icon(draw, info_x, y + 2, icon, fonts)
        else:
            draw_info_icon(draw, info_x, y + 2, icon, fonts)
        draw.text((info_x + 48, y - 22), label, font=load_font(fonts["label"]), fill=COLOR_MUTED)
        draw_fit_text(draw, (info_x + 48, y + 4), value, x1 - info_x - 76, fonts["body"], bold=True)
        if i < len(rows) - 1:
            line(draw, (info_x - 36, y + 62, x1 - 34, y + 62), fill=(32, 45, 66))
        y += 108

    status_y = y0 + 390
    reiatsu_icon_x = info_x + 4
    reiatsu_text_x = info_x + 74
    draw_flame_mark(draw, reiatsu_icon_x, status_y - 16, 0.50, COLOR_BLUE)
    draw.text((reiatsu_text_x, status_y), "REIATSU", font=load_font(fonts["body"]), fill=COLOR_MUTED)
    reiatsu_max = reiatsu_display_max(data)
    reiatsu_value = f"{fmt_number(data.get('reiatsu', 0))} / {fmt_number(reiatsu_max)}"
    draw_fit_text(draw, (reiatsu_text_x, status_y + 34), reiatsu_value, x1 - reiatsu_text_x - 42, fonts["race"] + 7, bold=True)
    draw_progress_bar(draw, (reiatsu_icon_x, status_y + 84, x1 - 48, status_y + 100), data.get("reiatsu", 0), reiatsu_max, COLOR_BLUE)


def hex_points(cx: int, cy: int, radius: int) -> List[Tuple[float, float]]:
    return [
        (cx + math.cos(math.radians(60 * i - 90)) * radius,
         cy + math.sin(math.radians(60 * i - 90)) * radius)
        for i in range(6)
    ]


def draw_hex_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int,
                  color: Tuple[int, int, int], symbol: str, font_size: int) -> None:
    pts = hex_points(cx, cy, radius)
    draw.line(pts + [pts[0]], fill=color, width=3)
    draw.text((cx, cy), symbol_text(symbol)[:2], font=load_symbol_font(font_size), fill=color, anchor="mm")


def get_attribute_color(attr: Dict[str, Any]) -> Tuple[int, int, int]:
    key = str(attr.get("color") or attr.get("key") or attr.get("title") or "").lower()
    return ATTRIBUTE_COLORS.get(key, COLOR_BLUE)


def attribute_defaults(attr: Dict[str, Any]) -> Tuple[str, str, str]:
    key = str(attr.get("key") or attr.get("title") or "").lower()
    default_title, default_desc, default_symbol = ATTRIBUTE_DEFAULTS.get(key, ("ATRIBUTO", "", "?"))
    return (
        str(attr.get("title") or attr.get("label") or default_title).upper(),
        str(attr.get("description") or default_desc).upper(),
        str(attr.get("symbol") or default_symbol),
    )


def modifier_lines(draw: ImageDraw.ImageDraw, attr: Dict[str, Any], font: ImageFont.ImageFont,
                   max_width: int, max_lines: int) -> List[str]:
    explicit = attr.get("modifier_text")
    if explicit is None:
        sources = attr.get("bonus_sources") or []
        explicit = "\n".join(str(item) for item in sources) if sources else attr.get("modifier_summary", "Sem modificadores")
    return wrap_text(draw, explicit, font, max_width, max_lines=max_lines)


def draw_attribute_card(draw: ImageDraw.ImageDraw, attr: Dict[str, Any], box: Box, fonts: Dict[str, int], compact: bool = False) -> None:
    x0, y0, x1, y1 = box
    color = get_attribute_color(attr)
    title, description, symbol = attribute_defaults(attr)
    rounded_rect(draw, box, radius=6, fill=COLOR_CARD, outline=COLOR_BORDER)

    h = y1 - y0
    icon_r = 58 if not compact else 55
    icon_x = x0 + (78 if not compact else 88)
    icon_y = y0 + h // 2
    draw_hex_icon(draw, icon_x, icon_y, icon_r, color, symbol, 52 if not compact else 48)

    title_x = x0 + (170 if not compact else 175)
    title_y = y0 + (41 if not compact else 48)
    draw_fit_text(draw, (title_x, title_y), title, 410 if not compact else 350, fonts["attr_title"], bold=True, display=True)
    desc_font = load_font(fonts["label"])
    for i, desc in enumerate(wrap_text(draw, description, desc_font, 420 if not compact else 360, max_lines=2)):
        draw.text((title_x, y0 + (99 if not compact else 112) + i * (fonts["label"] + 5)), desc, font=desc_font, fill=COLOR_MUTED)

    if not compact:
        base_center = x1 - 610
        current_center = x1 - 400
        bonus_x = x1 - 250
        stat_label_y = y0 + 53
        stat_value_y = y0 + 108
    else:
        base_center = x1 - 450
        current_center = x1 - 238
        bonus_x = x1 - 112
        stat_label_y = y0 + 75
        stat_value_y = y0 + 132

    line(draw, (base_center + 94, y0 + 38, base_center + 94, y1 - 38), fill=COLOR_BORDER_SOFT)
    draw.text((base_center, stat_label_y), "BASE", font=load_font(fonts["label"]), fill=COLOR_MUTED, anchor="mm")
    draw.text((base_center, stat_value_y), fmt_number(attr.get("base", 0)), font=load_font(fonts["attr_value"] - 10, bold=True), fill=COLOR_DIM, anchor="mm")
    draw.text((current_center, stat_label_y), "ATUAL", font=load_font(fonts["label"]), fill=COLOR_MUTED, anchor="mm")
    draw.text((current_center, stat_value_y), fmt_number(attr.get("current", attr.get("final", 0))), font=load_font(fonts["attr_value"], bold=True), fill=color, anchor="mm")

    bonus = attr.get("bonus")
    if bonus is None:
        try:
            bonus = int(attr.get("current", attr.get("final", 0))) - int(attr.get("base", 0))
        except (TypeError, ValueError):
            bonus = attr.get("modifier_total", "")
    bonus_text = f"{'+' if isinstance(bonus, (int, float)) and bonus >= 0 else ''}{fmt_number(bonus)}"
    draw_fit_text(draw, (bonus_x, y0 + (58 if not compact else 78)), bonus_text, x1 - bonus_x - 20, fonts["attr_bonus"], fill=color, bold=True, display=True)
    mfont = load_font(fonts["small"])
    for i, mod in enumerate(modifier_lines(draw, attr, mfont, x1 - bonus_x - 24, 3 if not compact else 2)):
        draw.text((bonus_x, y0 + (112 if not compact else 136) + i * (fonts["small"] + 5)), mod, font=mfont, fill=COLOR_MUTED)


def draw_attribute_cards(draw: ImageDraw.ImageDraw, data: Dict[str, Any], size: Tuple[int, int], fonts: Dict[str, int]) -> None:
    width, height = size
    attrs = data.get("attributes") or []
    if not is_mobile_size(size):
        x0, x1 = 428, 1760
        draw.text((x0 + 12, 196), str(data.get("intro", "DISTRIBUA PONTOS PARA FORTALECER SEU PERSONAGEM")), font=load_font(fonts["body"]), fill=COLOR_MUTED)
        y = 232
        card_h = 166
        gap = 18
        for attr in attrs[:3]:
            draw_attribute_card(draw, attr, (x0, y, x1, y + card_h), fonts, compact=False)
            y += card_h + gap
        return

    x0, x1 = 38, width - 38
    draw.text((x0 + 12, 752), str(data.get("intro", "DISTRIBUA PONTOS PARA FORTALECER SEU PERSONAGEM")), font=load_font(fonts["body"]), fill=COLOR_MUTED)
    y = 792
    for attr in attrs[:3]:
        draw_attribute_card(draw, attr, (x0, y, x1, y + 230), fonts, compact=True)
        y += 252


def draw_diamond_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int = 30) -> None:
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    draw.polygon(pts, fill=COLOR_TEXT)
    draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=COLOR_CARD)


def draw_footer(draw: ImageDraw.ImageDraw, data: Dict[str, Any], size: Tuple[int, int], fonts: Dict[str, int]) -> None:
    width, height = size
    derived = data.get("derived") or []
    if not derived:
        derived = [
            {"title": data.get("reiryoku_label", "REIRYOKU"), "value": f"{fmt_number(data.get('reiryoku', 0))} / {fmt_number(data.get('reiryoku_max', 0))}", "progress": data.get("reiryoku", 0), "progress_max": data.get("reiryoku_max", 1)},
            {"title": data.get("skill_points_label", "PONTOS DE PERÍCIA"), "value": fmt_number(data.get("pontos_pericia", 0))},
        ]

    if not is_mobile_size(size):
        x0, x1 = 428, 1760
        y0 = 828
        draw.text((x0 + 12, y0 - 16), str(data.get("derived_title", "ATRIBUTOS DERIVADOS")), font=load_font(fonts["body"], bold=True), fill=COLOR_TEXT)
        line(draw, (x0 + 245, y0 - 8, x1, y0 - 8), fill=(32, 45, 66))
        gap = 20
        box_w = (x1 - x0 - gap) // 2
        for i, item in enumerate(derived[:2]):
            bx0 = x0 + i * (box_w + gap)
            by0 = y0 + 22
            bx1 = bx0 + box_w
            by1 = by0 + 158
            rounded_rect(draw, (bx0, by0, bx1, by1), radius=6, fill=COLOR_CARD_SOFT, outline=COLOR_BORDER)
            if i == 0:
                draw_info_icon(draw, bx0 + 66, by0 + 58, "R", fonts)
            else:
                draw_diamond_icon(draw, bx0 + 66, by0 + 64, 30)
            draw.text((bx0 + 118, by0 + 38), str(item.get("title", "")).upper(), font=load_font(fonts["body"]), fill=COLOR_MUTED)
            value_y = by0 + (66 if item.get("progress") is not None else 78)
            draw_fit_text(draw, (bx0 + 118, value_y), item.get("value", ""), bx1 - bx0 - 150, fonts["race"] + 8, bold=True)
            if item.get("progress") is not None:
                draw_progress_bar(draw, (bx0 + 36, by1 - 42, bx1 - 36, by1 - 28), item.get("progress", 0), item.get("progress_max", 1), COLOR_BLUE)
        return

    x0, x1 = 38, width - 38
    y0 = height - 360
    draw.text((x0 + 12, y0), str(data.get("derived_title", "ATRIBUTOS DERIVADOS")), font=load_font(fonts["body"], bold=True), fill=COLOR_TEXT)
    line(draw, (x0 + 300, y0 + 12, x1, y0 + 12), fill=(32, 45, 66))
    y = y0 + 48
    for item in derived[:2]:
        rounded_rect(draw, (x0, y, x1, y + 128), radius=8, fill=COLOR_CARD_SOFT, outline=COLOR_BORDER)
        if item.get("progress") is not None:
            draw_info_icon(draw, x0 + 75, y + 58, "R", fonts)
        else:
            draw_diamond_icon(draw, x0 + 75, y + 64, 30)
        draw.text((x0 + 140, y + 20), str(item.get("title", "")).upper(), font=load_font(fonts["body"]), fill=COLOR_MUTED)
        value_y = y + (52 if item.get("progress") is not None else 62)
        draw_fit_text(draw, (x0 + 140, value_y), item.get("value", ""), x1 - x0 - 180, fonts["race"] + 8, bold=True)
        if item.get("progress") is not None:
            draw_progress_bar(draw, (x0 + 42, y + 98, x1 - 38, y + 113), item.get("progress", 0), item.get("progress_max", 1), COLOR_BLUE)
        y += 148


def normalize_attributes(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    attrs = profile.get("attributes") or []
    if isinstance(attrs, list):
        return attrs
    normalized: List[Dict[str, Any]] = []
    for key, attr in attrs.items():
        payload = dict(attr)
        payload.setdefault("key", key)
        payload.setdefault("title", attr.get("label", key.capitalize()))
        payload.setdefault("current", attr.get("final", attr.get("current", 0)))
        if "bonus" not in payload:
            try:
                payload["bonus"] = int(payload.get("current", 0)) - int(attr.get("base", 0))
            except (TypeError, ValueError):
                payload["bonus"] = attr.get("modifier_total", "")
        if "modifier_text" not in payload:
            sources = attr.get("bonus_sources") or []
            payload["modifier_text"] = "\n".join(sources) if sources else attr.get("modifier_summary", "Sem modificadores")
        normalized.append(payload)
    return normalized


def normalize_profile_data(profile: Dict[str, Any]) -> Dict[str, Any]:
    if not profile:
        return {}
    data = dict(profile)
    data["name"] = profile.get("name", profile.get("nome", "ARASHI"))
    data["race"] = profile.get("race", profile.get("raca", "SHINIGAMI"))
    data["spirit_level"] = profile.get("spirit_level", profile.get("nivel", "--"))
    data["potential"] = profile.get("potential", profile.get("potencial_nome", "Nenhum"))
    data["points_available"] = profile.get("points_available", profile.get("pontos_livres", 0))
    data["id"] = profile.get("id", profile.get("user_id", ""))
    data["attributes"] = normalize_attributes(profile)
    if "derived" not in data:
        data["derived"] = [
            {"title": "REIRYOKU", "value": f"{fmt_number(profile.get('reiryoku', 0))} / {fmt_number(profile.get('reiryoku_max', 0))}", "progress": profile.get("reiryoku", 0), "progress_max": profile.get("reiryoku_max", 1)},
            {"title": "PONTOS DE PERÍCIA", "value": fmt_number(profile.get("pontos_pericia", 0))},
        ]
    return data


def render_profile_card(data: Dict[str, Any], avatar_source: AvatarSource = None,
                        size: Tuple[int, int] = DESKTOP_SIZE) -> Image.Image:
    data = normalize_profile_data(data)
    fonts = MOBILE_FONT if is_mobile_size(size) else DESKTOP_FONT
    image = background_image(size).copy()
    draw = ImageDraw.Draw(image)
    draw_header(draw, data, size, fonts)
    draw_character_panel(image, draw, data, avatar_source, size, fonts)
    draw_attribute_cards(draw, data, size, fonts)
    draw_footer(draw, data, size, fonts)
    return image.filter(ImageFilter.UnsharpMask(radius=1.1, percent=105, threshold=3))


def save_png_buffer(image: Image.Image, compress_level: int = 1) -> BytesIO:
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", compress_level=compress_level)
    output.seek(0)
    return output


def create_profile_card(profile_data: Dict[str, Any], avatar_source: AvatarSource = None,
                        mobile: bool = False) -> BytesIO:
    size = MOBILE_SIZE if mobile else DESKTOP_SIZE
    image = render_profile_card(profile_data, avatar_source=avatar_source, size=size)
    return save_png_buffer(image)


EXAMPLE_PROFILE = {
    "name": "ARASHI",
    "race": "SHINIGAMI",
    "points_available": 0,
    "spirit_level": "Grande: Grau Baixo",
    "potential": "Nenhum",
    "reiatsu": 16500,
    "reiatsu_max": 16500,
    "reiatsu_cap": 30000,
    "reiryoku": 11000,
    "reiryoku_max": 11000,
    "pontos_pericia": 10,
    "attributes": [
        {"key": "forca", "title": "FORÇA", "description": "AUMENTA O PODER DE ATAQUE.", "base": 4000, "current": 6000, "bonus": 2000, "modifier_text": "Shinigami +50%"},
        {"key": "velocidade", "title": "VELOCIDADE", "description": "AUMENTA A AGILIDADE E ESQUIVA.", "base": 3000, "current": 4500, "bonus": 1500, "modifier_text": "Shinigami +50%"},
        {"key": "resistencia", "title": "RESISTÊNCIA", "description": "AUMENTA A DEFESA E RESILIÊNCIA.", "base": 4000, "current": 6000, "bonus": 2000, "modifier_text": "Shinigami +50%"},
    ],
    "footer": "Nemu v2.1",
}

if __name__ == "__main__":
    img = render_profile_card(EXAMPLE_PROFILE)
    img.convert("RGB").save("profile_preview.png", quality=95)
