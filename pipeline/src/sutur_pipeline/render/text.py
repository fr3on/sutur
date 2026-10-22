"""Arabic text with Pillow + Raqm: joined letters, right to left, wrapped by measured width."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageDraw, ImageFont, features

from ..errors import ConfigError


def require_raqm() -> None:
    if not features.check("raqm"):
        raise ConfigError("this Pillow has no Raqm (needed to join Arabic letters): use a Pillow build with libraqm")


@lru_cache(maxsize=256)
def font(path: Path, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size, index=index, layout_engine=ImageFont.Layout.RAQM)


def text_w(f: ImageFont.FreeTypeFont, s: str) -> float:
    return f.getlength(s, direction="rtl", language="ar")


def wrap(f: ImageFont.FreeTypeFont, text: str, max_w: float) -> list[str]:
    """Greedy word wrap in logical order; each returned line is one Arabic line (right to left). A lonely last word is pulled down from the line above."""
    lines: list[str] = []
    cur = ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if cur and text_w(f, t) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    if len(lines) > 1 and len(lines[-1].split()) == 1 and len(lines[-2].split()) > 2:
        last = lines[-2].split()
        lines[-1] = last.pop() + " " + lines[-1]
        lines[-2] = " ".join(last)
    return lines


def centered(
    d: ImageDraw.ImageDraw, s: str, cx: float, y: float, f: ImageFont.FreeTypeFont, fill: str = "black", stroke: int = 0, stroke_fill: str | None = None
) -> None:
    d.text((cx - text_w(f, s) / 2, y), s, font=f, fill=fill, direction="rtl", language="ar", stroke_width=stroke, stroke_fill=stroke_fill)


def fit(path: Path, s: str, max_w: float, size: int, index: int = 0, floor: int = 20) -> ImageFont.FreeTypeFont:
    """The largest font up to `size` (shrinking by 2) in which `s` fits `max_w`."""
    f = font(path, size, index)
    while text_w(f, s) > max_w and size > floor:
        size -= 2
        f = font(path, size, index)
    return f
