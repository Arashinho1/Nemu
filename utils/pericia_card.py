from functools import lru_cache
from pathlib import Path
import textwrap
import unicodedata

from PIL import Image, ImageDraw, ImageOps

from utils.pericia_service import get_player_pericias
from utils.profile_template import fit_font, load_font as load_profile_font, save_png_buffer


SCALE = 1.35
BASE_WIDTH = 1140
BASE_HEIGHT = 760
WIDTH = int(BASE_WIDTH * SCALE)
HEIGHT = int(BASE_HEIGHT * SCALE)
PAGE_SIZE = 2
ICON_DIR = Path(__file__).resolve().parents[1] / "assets" / "pericias"
ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

COLORS = {
    "bg": "#070a12",
    "panel": "#121827",
    "line": "#27344f",
    "text": "#f4f7ff",
    "muted": "#82a2d3",
    "blue": "#62b4ff",
    "gold": "#ffd35a",
    "green": "#62d394",
}


def _font(size, bold=False):
    return load_profile_font(int(size * SCALE), bold=bold, display=bold and size >= 26)


FONT = {
    "eyebrow": _font(15, True),
    "title": _font(54, True),
    "section": _font(18, True),
    "label": _font(15, True),
    "name": _font(26, True),
    "body": _font(17, False),
    "body_bold": _font(17, True),
    "points": _font(34, True),
    "icon": _font(28, True),
    "small": _font(15, False),
}


def _fmt(value):
    return f"{int(value):,}".replace(",", ".")


def _xy(x, y):
    return int(x * SCALE), int(y * SCALE)


def _box(box):
    return tuple(int(value * SCALE) for value in box)


def _text(draw, xy, text, font, fill="text", anchor=None):
    draw.text(_xy(*xy), str(text), font=font, fill=COLORS[fill], anchor=anchor)


def _fit_text(draw, xy, text, max_width, size, fill="text", min_size=9, bold=False, display=False, anchor=None):
    font, value = fit_font(
        draw,
        text,
        int(max_width * SCALE),
        int(size * SCALE),
        int(min_size * SCALE),
        bold=bold,
        display=display,
    )
    draw.text(_xy(*xy), value, font=font, fill=COLORS[fill], anchor=anchor)


def _rounded(draw, box, fill="panel", outline="line", radius=8, width=1):
    draw.rounded_rectangle(_box(box), radius=int(radius * SCALE), fill=COLORS[fill], outline=COLORS[outline], width=max(1, int(width * SCALE)))


def _line(draw, xy):
    draw.line(_box(xy), fill=COLORS["line"], width=max(1, int(SCALE)))


def _wrap(text, width=86, max_lines=3):
    text = (text or "Descricao ainda nao cadastrada.").replace("\n", " ")
    lines = textwrap.wrap(text, width=width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "..."
    return lines


def _slugify(text):
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = []
    for char in ascii_text.lower():
        cleaned.append(char if char.isalnum() else "_")
    slug = "".join(cleaned).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "pericia"


def _find_icon_path(name):
    slug = _slugify(name)
    if not ICON_DIR.exists():
        return None
    for path in sorted(ICON_DIR.iterdir(), key=lambda item: item.name.lower()):
        if path.is_file() and path.suffix.lower() in ICON_EXTENSIONS and _slugify(path.stem) == slug:
            return path
    return None


@lru_cache(maxsize=64)
def _load_fitted_icon(path_text, target_size):
    icon = Image.open(path_text).convert("RGBA")
    return ImageOps.fit(icon, (target_size, target_size), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _draw_icon(draw, x, y, size, name):
    _rounded(draw, (x, y, x + size, y + size), fill="bg", outline="line", radius=7)
    icon_path = _find_icon_path(name)
    if icon_path:
        try:
            target_size = int(size * SCALE)
            icon = _load_fitted_icon(str(icon_path), target_size).copy()
            left = int(x * SCALE)
            top = int(y * SCALE)
            draw._image.paste(icon, (left, top), icon)
            return
        except OSError:
            pass

    initials = "".join(part[0] for part in name.split()[:2]).upper() or "P"
    _text(draw, (x + size / 2, y + size / 2 - 2), initials, FONT["icon"], "blue", anchor="mm")


def _draw_bar(draw, x, y, w, h, percent):
    draw.rounded_rectangle(_box((x, y, x + w, y + h)), radius=int((h / 2) * SCALE), fill="#252b3c")
    fill_w = max(5, int(w * percent / 100))
    draw.rounded_rectangle(_box((x, y, x + fill_w, y + h)), radius=int((h / 2) * SCALE), fill=COLORS["blue"])


def _draw_pericia(draw, x, y, w, h, pericia, index, pp):
    _rounded(draw, (x, y, x + w, y + h))
    _text(draw, (x + 18, y + 18), f"{index}. {pericia['nome']}", FONT["name"], "text")
    _draw_icon(draw, x + 18, y + 58, 92, pericia["nome"])

    desc_x = x + 128
    for line_index, line in enumerate(_wrap(pericia["descricao"])):
        _text(draw, (desc_x, y + 60 + line_index * 22), line, FONT["body"], "text")

    info_y = y + 150
    _text(draw, (desc_x, info_y), f"Nivel atual: {pericia['nivel']}/6", FONT["body_bold"], "blue")
    _text(draw, (desc_x + 190, info_y), f"Bonus atual: {pericia['bonus_atual']}", FONT["body_bold"], "gold")

    custo = pericia["custo_proximo"]
    label = "Nivel maximo" if custo is None else f"PP investido / PP proximo nivel: {_fmt(pericia['pp_investido'])} / {_fmt(custo)}"
    _text(draw, (desc_x, y + h - 48), label, FONT["label"], "muted")
    _draw_bar(draw, desc_x, y + h - 24, w - 150, 10, pericia["progresso_pp"])


def create_pericia_card(user_id, page=0):
    data = get_player_pericias(user_id)
    if not data:
        return None, 0, []

    pericias = data["pericias"]
    total_pages = max(1, (len(pericias) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    visible = pericias[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    image = Image.new("RGB", (WIDTH, HEIGHT), COLORS["bg"])
    draw = ImageDraw.Draw(image)

    _text(draw, (15, 16), "NEMU RPG", FONT["eyebrow"], "blue")
    _text(draw, (15, 38), "PERICIAS", FONT["title"], "text")
    _rounded(draw, (935, 10, 1125, 90))
    _fit_text(draw, (1030, 42), _fmt(data["pontos_pericia"]), 160, 32, "gold", min_size=18, bold=True, display=True, anchor="mm")
    _fit_text(draw, (1030, 72), "PONTOS DE PERÍCIA", 160, 13, "muted", min_size=8, bold=True, anchor="mm")

    _text(draw, (18, 128), f"{data['nome']} - {data['raca']}", FONT["section"], "blue")
    _text(draw, (1122, 128), f"Pagina {page + 1}/{total_pages}", FONT["section"], "muted", anchor="ra")
    _line(draw, (15, 154, BASE_WIDTH - 15, 154))

    if not visible:
        _rounded(draw, (20, 190, 1120, 320))
        _text(draw, (40, 220), "Nenhuma pericia disponivel para este personagem.", FONT["name"], "text")
    else:
        y = 178
        for idx, pericia in enumerate(visible, start=1):
            _draw_pericia(draw, 20, y, 1100, 248, pericia, idx, data["pontos_pericia"])
            y += 268

    _text(draw, (15, 735), f"ID: {user_id} - Nemu v2.1", FONT["small"], "muted")

    return save_png_buffer(image), page, visible
