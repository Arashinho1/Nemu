from io import BytesIO
import time

import discord
from PIL import Image, ImageDraw


AVATAR_CACHE_TTL = 600
AVATAR_CACHE_MAX = 128
_avatar_cache = {}


async def read_discord_avatar(member, size=512):
    if not member:
        return None
    asset = member.display_avatar.replace(size=size, static_format="png")
    cache_key = (str(asset.url), size)
    now = time.monotonic()
    cached = _avatar_cache.get(cache_key)
    if cached and now - cached[0] <= AVATAR_CACHE_TTL:
        return cached[1]

    try:
        avatar = await asset.read()
    except discord.DiscordException:
        return None
    _avatar_cache[cache_key] = (now, avatar)
    if len(_avatar_cache) > AVATAR_CACHE_MAX:
        oldest_key = min(_avatar_cache, key=lambda key: _avatar_cache[key][0])
        _avatar_cache.pop(oldest_key, None)
    return avatar


def load_avatar_image(avatar_bytes):
    if not avatar_bytes:
        return None
    try:
        return Image.open(BytesIO(avatar_bytes)).convert("RGB")
    except OSError:
        return None


def cover_image(source, width, height):
    src_w, src_h = source.size
    scale = max(width / src_w, height / src_h)
    resized = source.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def circular_mask(size):
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask
