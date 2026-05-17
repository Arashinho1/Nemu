import re
import unicodedata


_SPLIT_RE = re.compile(r"\s*(?:,|;|/|\||\be\b|\bou\b)\s*", re.IGNORECASE)

_UNRESTRICTED_KEYS = {"", "nenhuma", "nenhum", "todos", "todas", "all"}
_ALL_KEYS = {"todos", "todas", "all"}
_NONE_KEYS = {"", "nenhuma", "nenhum"}

_RACE_ALIASES = {
    "arrancar": "arrancar",
    "fullbringer": "fullbringer",
    "fullbring": "fullbringer",
    "hibrido": "hibrido",
    "hibridos": "hibrido",
    "hollow": "hollow",
    "hollows": "hollow",
    "humano": "humanos",
    "humanos": "humanos",
    "quincy": "quincy",
    "shinigami": "shinigami",
    "shinigamis": "shinigami",
    "vaizard": "vaizard",
    "vizard": "vaizard",
    "visored": "vaizard",
}

_DISPLAY_LABELS = {
    "arrancar": "Arrancar",
    "fullbringer": "Fullbringer",
    "hibrido": "Hibrido",
    "hollow": "Hollow",
    "humanos": "Humanos",
    "quincy": "Quincy",
    "shinigami": "Shinigami",
    "vaizard": "Vaizard",
}

_HYBRID_RACE_INHERITANCE = {
    "vaizard": ("hibrido", "shinigami", "hollow"),
}


def _raw_race_key(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return "".join(char for char in ascii_text.casefold() if char.isalnum())


def race_key(value):
    key = _raw_race_key(value)
    return _RACE_ALIASES.get(key, key)


def split_race_restriction(value):
    text = str(value or "").strip()
    if not text:
        return ()

    text_key = race_key(text)
    if text_key in _UNRESTRICTED_KEYS:
        return ()

    races = []
    seen = set()
    for raw_part in _SPLIT_RE.split(text):
        part = raw_part.strip()
        key = race_key(part)
        if not key or key in _UNRESTRICTED_KEYS or key in seen:
            continue
        seen.add(key)
        races.append(_DISPLAY_LABELS.get(key, part))
    return tuple(races)


def normalize_race_restriction(value):
    text = str(value or "").strip()
    key = race_key(text)
    if key in _ALL_KEYS:
        return "Todos"
    if key in _NONE_KEYS:
        return "Nenhuma"

    races = split_race_restriction(text)
    return ", ".join(races) if races else "Nenhuma"


def race_restriction_keys(value):
    return {race_key(race) for race in split_race_restriction(value)}


def expanded_race_keys(races):
    keys = set()
    for race in races:
        raw_key = _raw_race_key(race)
        key = _RACE_ALIASES.get(raw_key, raw_key)
        if not key:
            continue

        keys.add(key)
        keys.update(_HYBRID_RACE_INHERITANCE.get(key, ()))

        for alias, canonical in _RACE_ALIASES.items():
            if alias and alias in raw_key:
                keys.add(canonical)
                keys.update(_HYBRID_RACE_INHERITANCE.get(canonical, ()))

    return keys


def race_restriction_allows(restriction, player_races):
    allowed_keys = race_restriction_keys(restriction)
    if not allowed_keys:
        return True
    return bool(allowed_keys & expanded_race_keys(player_races))
