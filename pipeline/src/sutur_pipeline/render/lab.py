"""The "behind the scenes" page right after the cover: the Sutur mark, name, a short note on how the book was made."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from ..layout import PAGE_H as H
from ..layout import PAGE_W as W
from .fonts import FontSet
from .text import centered, fit, font

NOTE = ["رسوم هذا الكتاب مولّدة بالذكاء الاصطناعي.", "النص الأصلي لمؤلفه ومترجمه،", "والرسوم وتنسيق الصفحات بترخيص"]


def _star(cx: float, cy: float, r: float, q: float) -> list[tuple[float, float]]:
    return [(cx + dx, cy + dy) for dx, dy in [(0, -r), (q, -q), (r, 0), (q, q), (0, r), (-q, q), (-r, 0), (-q, -q)]]


def logo(size: int) -> Image.Image:
    """The site's mark (a page with a spark and two lines in a rounded square), drawn at 4x and shrunk for clean edges."""
    k = size * 4 / 64
    im = Image.new("RGB", (size * 4, size * 4), "white")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, 64 * k, 64 * k], radius=14 * k, fill="black")
    d.rounded_rectangle([12 * k, 12 * k, 52 * k, 52 * k], radius=4 * k, fill="white")
    d.rounded_rectangle([17 * k, 40 * k, 35 * k, 43 * k], radius=1.5 * k, fill="black")
    d.rounded_rectangle([17 * k, 46 * k, 29 * k, 49 * k], radius=1.5 * k, fill="black")
    d.polygon([(x * k, y * k) for x, y in _star(37, 27, 15, 2.1)], fill="black")
    d.polygon([(x * k, y * k) for x, y in _star(21, 19, 5, 0.9)], fill="black")
    return im.resize((size, size), Image.Resampling.LANCZOS)


def compose_lab_page(fonts: FontSet) -> Image.Image:
    out = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(out)
    y = 330
    lat = ImageFont.truetype(str(fonts.latin), 112)
    icon, gap = 96, 24
    left, top, right, bottom = lat.getbbox("Sutur", stroke_width=2)   # ink box of the word, so the mark can be centred on it
    x0 = (W - (icon + gap + (right - left))) / 2
    out.paste(logo(icon), (int(x0), int(y + ((bottom - top) - icon) / 2)))
    d.text((x0 + icon + gap - left, y - top), "Sutur", font=lat, fill="black", stroke_width=2, stroke_fill="black")
    centered(d, "سطور", W / 2, y + 175, fit(fonts.vazir_bold, "سطور", 300, 80))
    tag = "كتب عربية مصوّرة بنمط المانغا"
    centered(d, tag, W / 2, y + 295, fit(fonts.vazir_regular, tag, W - 200, 40))
    d.rectangle((W / 2 - 120, y + 390, W / 2 + 120, y + 393), fill="black")
    centered(d, "وراء الكواليس", W / 2, y + 430, fit(fonts.vazir_bold, "وراء الكواليس", W - 160, 84))
    body = font(fonts.vazir_regular, 34)
    for i, line in enumerate(NOTE):
        centered(d, line, W / 2, y + 585 + i * 62, body)
    cc = ImageFont.truetype(str(fonts.latin), 46)
    d.text(((W - cc.getlength("CC BY 4.0")) / 2, y + 585 + len(NOTE) * 62 + 4), "CC BY 4.0", font=cc, fill="black", stroke_width=1, stroke_fill="black")
    foot = ImageFont.truetype(str(fonts.latin), 34)
    d.text(((W - foot.getlength("sutur.ink")) / 2, H - 150), "sutur.ink", font=foot, fill="black")
    return out
