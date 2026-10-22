"""The characters page: one portrait per character with name and role, three or four to a row, the first character at the right."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from PIL import Image, ImageDraw

from ..layout import PAGE_H as H
from ..layout import PAGE_W as W
from .fonts import FontSet
from .text import centered, fit, font, wrap

CastEntry = Sequence[str]   # id, Arabic name, Arabic role, portrait prompt


def compose_cast_page(cast: Sequence[CastEntry], portraits: Path, picks: Mapping[str, int], fonts: FontSet) -> Image.Image:
    out = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(out)
    centered(d, "الشخصيات", W / 2, 60, fit(fonts.title, "الشخصيات", W - 200, 120))
    d.rectangle((W / 2 - 120, 220, W / 2 + 120, 223), fill="black")
    cols = 3 if len(cast) <= 9 else 4   # ten or more characters: four to a row so the page does not overflow
    size, gap = (200, 28) if cols == 3 else (172, 18)
    for i, (cid, name, role, *_) in enumerate(cast):
        row, col = divmod(i, cols)
        n = min(cols, len(cast) - row * cols)
        x0 = int(W / 2 + (n * size + (n - 1) * gap) / 2 - size - col * (size + gap))
        y = 260 + row * 380
        im = Image.open(portraits / f"{cid}-s{picks.get(cid, 1)}.png").convert("L").convert("RGB")
        k = min(im.size)
        left, upper = (im.width - k) // 2, int(im.height * 0.02)
        im = im.crop((left, upper, left + int(k * 0.96), upper + int(k * 0.96))).resize((size, size), Image.Resampling.LANCZOS)
        out.paste(im, (x0, y))
        d.rectangle((x0, y, x0 + size, y + size), outline="black", width=4)
        cx = x0 + size / 2
        centered(d, name, cx, y + size + 12, fit(fonts.body, name, size, 30))
        role_font = font(fonts.body, 20)
        yy = y + size + 52
        for line in wrap(role_font, role, size):
            centered(d, line, cx, yy, role_font)
            yy += 28
    return out
