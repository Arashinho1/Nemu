import math

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from utils.avatar import cover_image, load_avatar_image
from utils.profile_service import get_profile_data
from utils.profile_template import save_png_buffer


WIDTH = 1024
HEIGHT = 1536

BG = (2, 7, 18)
PANEL = (0, 9, 25)
BORDER = (24, 44, 73)
WHITE = (242, 244, 250)
MUTED = (155, 174, 210)
DIM = (95, 108, 138)
BLUE = (58, 157, 255)
RED = (255, 80, 95)
YELLOW = (255, 201, 60)
BAR = (28, 36, 58)

ATTR_META = {
    "forca": ("FORCA", "AUMENTA O PODER DE ATAQUE.", RED, "F"),
    "velocidade": ("VELOCIDADE", "AUMENTA A AGILIDADE E ESQUIVA.", BLUE, "V"),
    "resistencia": ("RESISTENCIA", "AUMENTA A DEFESA E RESILIENCIA.", YELLOW, "R"),
}


def _fmt(value):
    try:
        number = float(value)
        if math.isinf(number):
            return "∞"
        return f"{int(number):,}".replace(",", ".")
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _font(size, bold=False, display=False):
    names = []
    if display:
        names.extend(["impact.ttf", "bahnschrift.ttf"])
    if bold:
        names.extend(["bahnschrift.ttf", "arialbd.ttf", "segoeuib.ttf"])
    names.extend(["bahnschrift.ttf", "arial.ttf", "segoeui.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_size(draw, text, font):
    box = draw.textbbox((0, 0), str(text), font=font)
    return box[2] - box[0], box[3] - box[1]


def _fit(draw, text, max_width, size, min_size=12, bold=False, display=False):
    text = str(text)
    while size >= min_size:
        font = _font(size, bold=bold, display=display)
        if _text_size(draw, text, font)[0] <= max_width:
            return font, text
        size -= 1
    font = _font(min_size, bold=bold, display=display)
    ellipsis = "..."
    while text and _text_size(draw, text + ellipsis, font)[0] > max_width:
        text = text[:-1]
    return font, (text + ellipsis) if text else ellipsis


def _draw_fit(draw, xy, text, max_width, size, fill=WHITE, min_size=12, bold=False, display=False, anchor=None):
    font, value = _fit(draw, text, max_width, size, min_size, bold, display)
    draw.text(xy, value, font=font, fill=fill, anchor=anchor)


def _rounded(draw, box, radius=8, fill=None, outline=BORDER, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _line(draw, xy, fill=BORDER, width=1):
    draw.line(xy, fill=fill, width=width)


def _progress(draw, box, value, max_value, color=BLUE):
    _rounded(draw, box, radius=max(2, (box[3] - box[1]) // 2), fill=BAR, outline=None)
    ratio = 0 if not max_value else max(0, min(1, value / max_value))
    fill_w = max(4, int((box[2] - box[0]) * ratio))
    _rounded(draw, (box[0], box[1], box[0] + fill_w, box[3]), radius=max(2, (box[3] - box[1]) // 2), fill=color, outline=None)


def _hex_points(cx, cy, radius):
    return [
        (cx + math.cos(math.radians(60 * i - 90)) * radius, cy + math.sin(math.radians(60 * i - 90)) * radius)
        for i in range(6)
    ]


def _hex_icon(draw, cx, cy, radius, color, letter, font_size=58):
    points = _hex_points(cx, cy, radius)
    draw.line(points + [points[0]], fill=color, width=3)
    font = _font(font_size, bold=True, display=True)
    draw.text((cx, cy - 2), letter, font=font, fill=color, anchor="mm")


def _circle_icon(draw, center, radius, color=WHITE, label=""):
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=3)
    if label:
        draw.text((x, y + 1), label, font=_font(radius + 8, bold=True, display=True), fill=color, anchor="mm")


def _draw_background(image, draw):
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=BG)
    for y in range(0, HEIGHT, 140):
        draw.line((0, y, WIDTH, y + 220), fill=(4, 12, 28), width=1)
    for offset in range(0, 360, 22):
        draw.polygon(
            [(256 + offset, 0), (520 + offset, 0), (342 + offset, 130), (140 + offset, 130)],
            fill=(7, 15, 32),
        )
    brush = Image.new("RGBA", (520, 150), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(brush)
    for i in range(18):
        y = 18 + i * 6
        bdraw.line((60 + i * 8, y, 470 - i * 5, y - 38), fill=(20, 31, 52, 150), width=max(2, 9 - i // 2))
    image.alpha_composite(brush, (330, 0))


def _draw_logo_mark(draw, x, y, color=WHITE):
    points = [(x, y + 60), (x + 20, y + 25), (x + 34, y + 52), (x + 45, y), (x + 64, y + 54), (x + 82, y + 22), (x + 74, y + 84), (x + 42, y + 104)]
    draw.polygon(points, fill=color)


def _draw_header(draw, profile):
    draw.rectangle((0, 0, WIDTH, 130), fill=(4, 10, 24))
    _draw_logo_mark(draw, 36, 30)
    draw.text((116, 28), "ATRIBUTOS", font=_font(46, bold=True, display=True), fill=WHITE)
    draw.text((116, 82), "属性メニュー", font=_font(18), fill=BLUE)

    for i in range(5):
        draw.rectangle((148 + i * 22, 68, 162 + i * 22, 76), fill=BLUE)

    _line(draw, (620, 42, 620, 118), fill=(76, 96, 128), width=1)

    right_x = 998
    sep_x = 620
    # Draw points number using a fitted font so it never overflows into the left area
    points_text = _fmt(profile.get("pontos_livres", "0"))
    points_max_width = max(80, right_x - sep_x - 24)
    points_font, points_value = _fit(draw, points_text, points_max_width, 72, min_size=18, bold=True, display=True)
    draw.text((right_x, 28), points_value, font=points_font, fill=BLUE, anchor="rm")

    # Draw points label, also fitted
    label_font, label_value = _fit(draw, "PONTOS DISPONIVEIS", points_max_width, 18, min_size=10, bold=True)
    draw.text((right_x, 80), label_value, font=label_font, fill=WHITE, anchor="rm")

    draw.text((right_x, 104), "Nemu", font=_font(14), fill=WHITE, anchor="rm")

    # Draw BLEACH left of the points block but ensure it doesn't overlap
    bleach_font = _font(28, bold=True, display=True)
    bleach_w, bleach_h = _text_size(draw, "BLEACH", bleach_font)
    preferred_bleach_x = 732
    max_bleach_x = right_x - bleach_w - 16
    if max_bleach_x < sep_x + 12:
        bleach_x = sep_x + 12
    else:
        bleach_x = min(preferred_bleach_x, max_bleach_x)
    draw.text((bleach_x, 64), "BLEACH", font=bleach_font, fill=WHITE, anchor="lm")


def _draw_portrait(image, draw, avatar):
    box = (26, 146, 380, 486)
    _rounded(draw, (24, 130, 1000, 486), radius=7, fill=PANEL, outline=BORDER, width=1)
    _rounded(draw, box, radius=7, fill=(4, 12, 26), outline=(44, 205, 255), width=2)
    inner = (32, 152, 378, 484)
    if avatar:
        portrait = cover_image(avatar.convert("RGB"), inner[2] - inner[0], inner[3] - inner[1]).convert("RGBA")
        portrait = ImageEnhance.Color(portrait).enhance(0.28)
        portrait = ImageEnhance.Contrast(portrait).enhance(1.18)
        shade = Image.new("RGBA", portrait.size, (0, 12, 28, 96))
        portrait = Image.alpha_composite(portrait, shade)
        mask = Image.new("L", portrait.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, portrait.width - 1, portrait.height - 1), radius=7, fill=255)
        image.paste(portrait, (inner[0], inner[1]), mask)
    else:
        draw.text((202, 318), "SEM IMAGEM", font=_font(28, bold=True), fill=DIM, anchor="mm")
    draw.text((202, 246), "BLEACH", font=_font(58, bold=True, display=True), fill=(255, 255, 255, 24), anchor="mm")


def _draw_profile(draw, profile):
    x = 436
    _draw_fit(draw, (x, 170), str(profile["nome"]).upper(), 520, 52, bold=True, display=True)
    _draw_fit(draw, (x, 230), str(profile["raca"]).upper(), 520, 28, fill=BLUE, bold=True)
    draw.rectangle((426, 150, 972, 482), outline=(34, 58, 102), width=1)
    _line(draw, (426, 264, 972, 264), fill=(34, 58, 102), width=1)

    rows = [
        ("NIVEL ESPIRITUAL", profile["nivel"], "N"),
        ("RACA", profile["raca"], "!"),
        ("POTENCIAL", profile["potencial_nome"], "P"),
    ]
    y = 312
    for i, (label, value, icon) in enumerate(rows):
        _circle_icon(draw, (458, y), 20, WHITE, icon)
        draw.text((496, y - 16), label, font=_font(20), fill=MUTED)
        _draw_fit(draw, (496, y + 18), value, 430, 24, fill=WHITE, bold=True)
        if i != len(rows) - 1:
            _line(draw, (426, y + 44, 972, y + 44), fill=(34, 58, 102), width=1)
        y += 78


def _draw_energy(draw, profile):
    _rounded(draw, (24, 504, 1000, 634), radius=7, fill=PANEL, outline=BORDER)
    _rounded(draw, (24, 504, 506, 634), radius=7, fill=None, outline=(34, 58, 102), width=1)
    _rounded(draw, (506, 504, 1000, 634), radius=7, fill=None, outline=(34, 58, 102), width=1)
    _line(draw, (506, 520, 506, 618), fill=(70, 88, 122), width=1)

    _draw_logo_mark(draw, 52, 548, BLUE)
    draw.text((138, 526), "REIATSU", font=_font(22), fill=MUTED)
    reiatsu_max = profile.get("reiatsu_max", profile.get("reiatsu_cap", 1))
    draw.text((138, 564), f"{_fmt(profile['reiatsu'])} / {_fmt(reiatsu_max)}", font=_font(30, bold=True), fill=WHITE)
    _progress(draw, (60, 600, 470, 612), profile["reiatsu"], reiatsu_max, BLUE)

    _circle_icon(draw, (582, 556), 24, WHITE, "R")
    draw.text((646, 526), "REIRYOKU", font=_font(22), fill=MUTED)
    draw.text((646, 564), f"{_fmt(profile['reiryoku'])} / {_fmt(profile['reiryoku_max'])}", font=_font(30, bold=True), fill=WHITE)
    _progress(draw, (555, 600, 965, 612), profile["reiryoku"], profile["reiryoku_max"], BLUE)


def _modifier_text(attr):
    sources = attr.get("bonus_sources") or []
    return sources[0] if sources else attr.get("modifier_summary", "Sem modificadores")


def _draw_stat_card(draw, y, attr):
    title, desc, color, letter = ATTR_META[attr["key"]]
    _rounded(draw, (24, y, 1000, y + 196), radius=7, fill=PANEL, outline=BORDER)
    _hex_icon(draw, 112, y + 88, 56, color, letter)
    draw.text((194, y + 36), title, font=_font(46, bold=True, display=True), fill=WHITE)
    draw.text((194, y + 92), desc, font=_font(18), fill=MUTED)

    draw.text((334, y + 122), "BASE", font=_font(18), fill=MUTED, anchor="mm")
    draw.text((334, y + 154), _fmt(attr["base"]), font=_font(36, bold=True), fill=DIM, anchor="mm")
    _line(draw, (430, y + 114, 430, y + 176), fill=(82, 101, 132), width=1)
    draw.text((542, y + 122), "ATUAL", font=_font(18), fill=MUTED, anchor="mm")
    draw.text((542, y + 154), _fmt(attr["final"]), font=_font(42, bold=True), fill=color, anchor="mm")

    bonus = attr["bonus"]
    sign = "+" if bonus >= 0 else ""
    draw.text((754, y + 72), f"{sign}{_fmt(bonus)}", font=_font(36, bold=True), fill=color)
    _draw_fit(draw, (724, y + 126), _modifier_text(attr), 156, 18, fill=MUTED, min_size=11)
    _rounded(draw, (896, y + 68, 966, y + 138), radius=8, fill=None, outline=color, width=2)
    draw.text((931, y + 103), "+", font=_font(50, bold=True), fill=color, anchor="mm")


def _draw_derived(draw, profile):
    y = 1328
    _line(draw, (24, y, 58, y))
    draw.text((74, y - 15), "ATRIBUTOS DERIVADOS", font=_font(20), fill=MUTED)
    _line(draw, (300, y, 1000, y))
    _rounded(draw, (24, 1354, 510, 1478), radius=7, fill=PANEL, outline=BORDER)
    _rounded(draw, (514, 1354, 1000, 1478), radius=7, fill=PANEL, outline=BORDER)

    _circle_icon(draw, (88, 1416), 23, WHITE, "R")
    draw.text((140, 1380), "REIRYOKU", font=_font(20), fill=MUTED)
    draw.text((140, 1415), f"{_fmt(profile['reiryoku'])} / {_fmt(profile['reiryoku_max'])}", font=_font(28, bold=True), fill=WHITE)
    _progress(draw, (66, 1450, 470, 1462), profile["reiryoku"], profile["reiryoku_max"], BLUE)

    draw.polygon([(562, 1416), (582, 1392), (602, 1416), (582, 1440)], fill=WHITE)
    draw.ellipse((572, 1406, 592, 1426), fill=PANEL)
    draw.text((612, 1380), "PONTOS DE PERICIA", font=_font(20), fill=MUTED)
    draw.text((612, 1418), _fmt(profile["pontos_pericia"]), font=_font(32, bold=True), fill=WHITE)

    _line(draw, (24, 1510, 236, 1510), fill=(80, 100, 132))
    draw.text((258, 1494), f"ID: {profile['user_id']}", font=_font(16), fill=MUTED)
    draw.text((496, 1500), "Nemu v2.1", font=_font(16), fill=MUTED)
    _line(draw, (692, 1510, 1000, 1510), fill=(80, 100, 132))


def create_profile_card(user_id, avatar_bytes=None, profile=None):
    profile = profile or get_profile_data(user_id)
    if not profile:
        return None

    avatar = load_avatar_image(avatar_bytes)
    image = Image.new("RGBA", (WIDTH, HEIGHT), BG + (255,))
    draw = ImageDraw.Draw(image)
    _draw_background(image, draw)
    _draw_header(draw, profile)
    _draw_portrait(image, draw, avatar)
    _draw_profile(draw, profile)
    _draw_energy(draw, profile)
    _line(draw, (24, 670, 60, 670))
    draw.text((76, 654), "DISTRIBUA PONTOS PARA FORTALECER SEU PERSONAGEM", font=_font(20), fill=MUTED)

    y = 696
    for key in ("forca", "velocidade", "resistencia"):
        _draw_stat_card(draw, y, profile["attributes"][key])
        y += 204
    _draw_derived(draw, profile)

    image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=3))
    return save_png_buffer(image)
