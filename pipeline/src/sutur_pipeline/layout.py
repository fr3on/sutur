"""Page geometry: where each panel sits on the 864x1440 page and at what size the model should draw it."""

from __future__ import annotations

from typing import Any

PAGE_W, PAGE_H, MARGIN, GUTTER = 864, 1440, 14, 10

Box = tuple[int, int, int, int]   # x0, y0, x1, y1


def panel_boxes(rows: list[dict[str, Any]]) -> dict[str, Box]:
    """Pixel box of every panel id. Rows go top to bottom, panels inside a row right to left (manga order); `h` and `w` are relative."""
    inner_h = PAGE_H - 2 * MARGIN - GUTTER * (len(rows) - 1)
    total_h = sum(r["h"] for r in rows)
    boxes: dict[str, Box] = {}
    y = MARGIN
    for row in rows:
        row_h = round(inner_h * row["h"] / total_h)
        panels = row["panels"]
        inner_w = PAGE_W - 2 * MARGIN - GUTTER * (len(panels) - 1)
        total_w = sum(p.get("w", 1) for p in panels)
        x = PAGE_W - MARGIN
        for p in panels:
            width = round(inner_w * p.get("w", 1) / total_w)
            boxes[p["id"]] = (x - width, y, x, y + row_h)
            x -= width + GUTTER
        y += row_h + GUTTER
    return boxes


def draw_size(box: Box, longest: int = 1024, step: int = 32, floor: int = 256) -> tuple[int, int]:
    """Size to request from the model: the box scaled so its longer side is `longest`, both sides rounded to the model's step."""
    w, h = box[2] - box[0], box[3] - box[1]
    k = longest / max(w, h)
    return max(floor, round(w * k / step) * step), max(floor, round(h * k / step) * step)
