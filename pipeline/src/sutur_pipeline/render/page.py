"""Assemble a manga page from the drawn panels: each panel is its own picture, with the caption in a white strip at the top (sized to the text) and the
picture filling the rest, so no face is covered. Captions are lettered in code, never by the image model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageStat

from ..layout import PAGE_H, PAGE_W
from ..models import PageSpec
from ..source import BookText
from .fonts import FontSet
from .text import font, text_w, wrap

CAPTION_SIZES = range(17, 10, -1)     # largest first
CAPTION_MAX_SHARE = 0.45              # the caption strip may take at most this much of the panel height


@dataclass
class PageResult:
    image: Image.Image
    omitted: list[str] = field(default_factory=list)   # panels whose caption needed an oversize strip


def cover_fit(im: Image.Image, size: tuple[int, int], trim: float = 0.035, y_bias: float = 0.5) -> Image.Image:
    """Grayscale, trim the model's own frame, scale to cover `size` and crop. y_bias 0 keeps the top of the picture (heads), 0.5 centres."""
    im = im.convert("L").convert("RGB")   # the books are black and white: drop any colour the model added
    w, h = im.size
    im = im.crop((int(w * trim), int(h * trim), int(w * (1 - trim)), int(h * (1 - trim))))
    k = max(size[0] / im.width, size[1] / im.height)
    im = im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.LANCZOS)
    x, y = (im.width - size[0]) // 2, round((im.height - size[1]) * y_bias)
    return im.crop((x, y, x + size[0], y + size[1]))


def has_black_side_bars(path: Path) -> bool:
    """A picture with a solid black band on its left or right edge (the model sometimes draws a frame): its caption strip would look broken."""
    im = Image.open(path).convert("L")
    k = max(6, int(im.width * 0.05))
    for box in ((0, 0, k, im.height), (im.width - k, 0, im.width, im.height)):
        st = ImageStat.Stat(im.crop(box))
        if st.mean[0] < 25 and st.stddev[0] < 8:
            return True
    return False


def choose_picks(spec: PageSpec, overrides: Mapping[str, int] | None = None) -> dict[str, int]:
    """Per panel the first seed (in the spec's order) whose picture exists and has no black side bars; `overrides` ({"e": 12}) win."""
    picks: dict[str, int] = {}
    for p in spec.panels():
        for seed in spec.seeds_for(p):
            f = spec.pictures_dir / f"{p['id']}-s{seed}.png"
            if f.exists() and not has_black_side_bars(f):
                picks[p["id"]] = seed
                break
    picks.update(overrides or {})
    return picks


def compose_page(spec: PageSpec, picks: Mapping[str, int], book: BookText, fonts: FontSet) -> PageResult:
    boxes = spec.boxes()
    flat = [(p, k) for p, cs in enumerate(book.plain_clauses, start=1) for k in range(len(cs))]
    page = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    d = ImageDraw.Draw(page)
    omitted: list[str] = []
    for panel in spec.panels():
        pid = panel["id"]
        x0, y0, x1, y1 = boxes[pid]
        top, lines, f, size = y0, [], None, 11
        if panel.get("text"):
            (a1, a2), (b1, b2) = (tuple(map(int, s.split("."))) for s in panel["text"])
            text = " ".join(book.plain_clauses[p - 1][k] for p, k in flat[flat.index((a1, a2)) : flat.index((b1, b2)) + 1])
            width = (x1 - x0) - 16
            th = 0
            for size in CAPTION_SIZES:   # noqa: B007 - `size` is read after the loop
                f = font(fonts.caption, size)
                lines = wrap(f, text, width - 12)
                th = len(lines) * size + (len(lines) - 1) * int(size * 0.25) + 14
                if th <= (y1 - y0) * CAPTION_MAX_SHARE:
                    break
            else:
                omitted.append(pid)
            top = y0 + th + 6
        files = sorted(spec.pictures_dir.glob(f"{pid}-s*.png"))
        chosen = next((q for q in files if q.stem.endswith(f"-s{picks.get(pid)}")), files[0])
        page.paste(cover_fit(Image.open(chosen), (x1 - x0, y1 - top), y_bias=spec.data.get("crop_y", 0.5)), (x0, top))
        d.rectangle((x0, y0, x1 - 1, y1 - 1), outline="black", width=3)
        if lines and f is not None:
            d.rectangle((x0 + 2, y0 + 2, x1 - 3, top - 1), fill="white")
            d.line((x0, top - 1, x1, top - 1), fill="black", width=2)
            yy = y0 + 8
            for line in lines:
                d.text(((x0 + x1) / 2 - text_w(f, line) / 2, yy), line, font=f, fill="black", direction="rtl", language="ar")
                yy += size + int(size * 0.25)
    return PageResult(page, omitted)


def contact_sheets(pages: list[Path], per_sheet: int = 6) -> list[Image.Image]:
    """Review sheets: six built pages each, three across."""
    sheets = []
    for i in range(0, len(pages), per_sheet):
        sheet = Image.new("RGB", (3 * 330, 2 * 550), "white")
        for j, f in enumerate(pages[i : i + per_sheet]):
            sheet.paste(Image.open(f).convert("RGB").resize((324, 540), Image.Resampling.LANCZOS), ((j % 3) * 330 + 3, (j // 3) * 550 + 5))
        sheets.append(sheet)
    return sheets
