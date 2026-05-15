from PIL import Image, ImageDraw, ImageFilter


def draw_glow_bar(image, box, percent, fill, track="#252b3c", radius=5, glow=True):
    draw = ImageDraw.Draw(image)
    x1, y1, x2, y2 = [int(v) for v in box]
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    fill_w = max(2, int(width * max(0, min(100, percent)) / 100))

    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=track)
    if glow:
        glow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_draw.rounded_rectangle((x1, y1, x1 + fill_w, y2), radius=radius, fill=fill)
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(max(2, height // 2)))
        image.paste(glow_layer, (0, 0), glow_layer)
    draw.rounded_rectangle((x1, y1, x1 + fill_w, y2), radius=radius, fill=fill)
