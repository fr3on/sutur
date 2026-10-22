"""Volume cover: the art (made black and white) fading to white, series line, volume number, title and author drawn by code."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageOps

from ..layout import PAGE_H as H
from ..layout import PAGE_W as W
from .fonts import FontSet
from .text import centered, fit


def compose_cover(art: Image.Image, fonts: FontSet, series: str, volume: str, title: str, author: str) -> Image.Image:
    im = ImageOps.autocontrast(art.convert("L"), cutoff=1).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
    fade = Image.linear_gradient("L").resize((W, 300)).point(lambda v: min(255, int(v * 1.6)))
    mask = Image.new("L", (W, H), 0)
    mask.paste(fade, (0, H - 300))
    top = Image.linear_gradient("L").resize((W, 160)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).point(lambda v: int(v * 0.9))
    mask.paste(top, (0, 0))
    im = Image.composite(Image.new("RGB", (W, H), "white"), im, mask)
    d = ImageDraw.Draw(im)
    centered(d, series, W / 2, 28, fit(fonts.body, series, W - 200, 44))
    centered(d, title, W / 2, 1060, fit(fonts.title, title, W - 120, 130), stroke=6, stroke_fill="white")
    d.rectangle((W / 2 - 150, 1230, W / 2 + 150, 1233), fill="black")
    centered(d, volume, W / 2, 1250, fit(fonts.body, volume, W - 200, 40))
    centered(d, author, W / 2, 1330, fit(fonts.body, author, W - 200, 34))
    return im


def cover_sheet(files: list[Image.Image]) -> Image.Image:
    """Contact sheet of cover candidates to choose from (288x480 each)."""
    sheet = Image.new("RGB", (len(files) * 290, 480), "white")
    for i, im in enumerate(files):
        sheet.paste(im.convert("RGB").resize((288, 480)), (i * 290, 0))
    return sheet
