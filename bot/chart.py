from __future__ import annotations

import os
from io import BytesIO

_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def render_category_chart(rows: list[tuple[str, float]]) -> bytes | None:
    positive = [(name, float(total)) for name, total in rows if total > 0]
    if not positive:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    font = _font(ImageFont, 18)
    title_font = _font(ImageFont, 22)
    width = 760
    row_height = 36
    height = 64 + row_height * len(positive)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((24, 16), "Суммы категорий за всё время", fill="#1f2933", font=title_font)
    maximum = max(total for _, total in positive)
    bar_left = 250
    bar_max = 360
    top = 56
    for index, (name, total) in enumerate(positive):
        y = top + index * row_height
        draw.text((24, y + 6), name[:28], fill="#1f2933", font=font)
        bar_width = max(1, int(bar_max * total / maximum))
        draw.rectangle(
            (bar_left, y + 6, bar_left + bar_width, y + 26),
            fill="#3b82f6",
        )
        draw.text(
            (bar_left + bar_width + 8, y + 6),
            f"{total:.0f}",
            fill="#1f2933",
            font=font,
        )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _font(image_font, size: int):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return image_font.truetype(path, size)
            except OSError:
                continue
    return image_font.load_default()
