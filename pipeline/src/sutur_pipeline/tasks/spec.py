"""Spec task: the page specs (`pages/pNN.json`) from `prompts.txt`, `tags.json` and `starts.json`.

Pages hold 6 panels (the last few pages 5 so the count works out), laid out from a few fixed designs. Tall figures (tags.giants) get the head-in-frame hint and
seeds 11-13, every other panel seeds 1-3. Each panel's `text` is the clause range [its start, the clause before the next start]."""

from __future__ import annotations

import json
import re
from typing import Any

from ..errors import SpecError
from ..volume import resolve
from .base import Context, Kind, Result, Task
from .registry import register

HINT = "Medium shot with the whole head and face clearly in the frame."
LAYOUTS: dict[int, list[list[tuple[float, list[float]]]]] = {
    6: [[(0.26, [1]), (0.28, [1.1, 1]), (0.23, [1, 1]), (0.23, [1])],
        [(0.23, [1.1, 1]), (0.30, [1]), (0.24, [1, 1.1]), (0.23, [1])],
        [(0.30, [1]), (0.23, [1.2, 1]), (0.24, [1, 1]), (0.23, [1])]],
    5: [[(0.28, [1]), (0.36, [1, 1]), (0.36, [1.2, 1])]],
    4: [[(0.28, [1]), (0.36, [1, 1]), (0.36, [1])]],    # only for short volumes (see page_sizes)
    3: [[(0.40, [1]), (0.60, [1, 1])]],
    2: [[(0.50, [1]), (0.50, [1])]],
    1: [[(1.0, [1])]],
}
_QUOTED = re.compile(r"[\"“”][^\"“”]*[\"“”]")
_OPEN_QUOTE = re.compile(r"[\"“”][^\"“”]*$")
_SPEECH_VERBS = re.compile(r"\b(says|said|saying|asks|asked|replies|replied|exclaims|whispers|shouts|tells)\b[ ,:]*")


def page_sizes(n: int) -> list[int]:
    """Panels per page: sixes with just enough fives at the end for the count to work out (the layout the finished volumes use).

    That only works from 20 panels up (or when n is a multiple of 6); a shorter volume gets evenly filled pages of at most six instead."""
    if n < 1:
        raise SpecError("a volume needs at least one panel")
    fives = (6 - n % 6) % 6 if n % 6 else 0
    if n >= 5 * fives:
        return [6] * ((n - 5 * fives) // 6) + [5] * fives
    pages = -(-n // 6)
    return [n // pages + (1 if i < n % pages else 0) for i in range(pages)]


def final_prompt(prompt: str, index: int, tags: dict[str, Any]) -> tuple[str, bool]:
    """The drawing prompt (tags expanded, bubble-inducing words removed, tall-figure hint added) and whether the panel shows a tall figure."""
    if index >= tags.get("swap_from", 10**9):
        for a, b in tags["swap"].items():
            prompt = prompt.replace("{" + a + "}", "{" + b + "}")
    tall = any("{" + g + "}" in prompt for g in tags["giants"])
    for k, v in tags["tags"].items():
        prompt = prompt.replace("{" + k + "}", v)
    for extra in tags.get("auto", []):   # extra wording only for panels that need it (the weapon, the hands), not in every panel
        if any(w in prompt.lower() for w in extra["words"]):
            prompt = prompt + ", " + extra["text"]
    prompt = _QUOTED.sub("", prompt)           # quoted words in a prompt get drawn as speech bubbles
    prompt = _OPEN_QUOTE.sub("", prompt)       # an unmatched opening quote: drop the rest of the sentence
    prompt = prompt.replace('"', "").replace("“", "").replace("”", "")
    prompt = _SPEECH_VERBS.sub("", prompt)     # dialogue verbs make the model draw bubbles
    prompt = re.sub(r"\{[^}]*\}", "a figure", prompt)   # a tag the LLM invented: draw a plain figure instead of failing
    prompt = prompt.replace("{", "").replace("}", "")
    return (HINT + " " + prompt if tall else prompt), tall


def build_pages(prompts: list[str], starts: list[str], tags: dict[str, Any], order: list[str], last: str, book: str, chapter: int) -> dict[str, dict[str, Any]]:
    """`{"p01": spec, ...}` for the volume. `order` lists every clause id of the chapter in reading order, `last` is the last clause of the volume."""
    if len(prompts) != len(starts) or not all(prompts):
        raise SpecError(f"prompts.txt has {len(prompts)} lines (blank ones not allowed) but starts.json has {len(starts)} panels")
    sizes = page_sizes(len(prompts))
    pages: dict[str, dict[str, Any]] = {}
    i = 0
    for number, size in enumerate(sizes, start=1):
        panels = []
        for j in range(size):
            prompt, tall = final_prompt(prompts[i], i, tags)
            end = order.index(starts[i + 1]) - 1 if i + 1 < len(starts) else order.index(last)
            panels.append({"id": "abcdef"[j], "prompt": prompt, "text": [starts[i], order[end]], "seeds": [11, 12, 13] if tall else [1, 2, 3]})
            i += 1
        layout = LAYOUTS[size][(number - 1) % len(LAYOUTS[size])]
        it = iter(panels)
        rows = [{"h": h, "panels": [dict(next(it), w=w) for w in widths]} for h, widths in layout]
        pages[f"p{number:02d}"] = {"book": book, "chapter": chapter, "crop_y": 0.0, "prefix": tags["prefix"], "suffix": tags["suffix"], "rows": rows}
    return pages


@register
class SpecTask(Task):
    name = "spec"
    kind = Kind.TRANSFORM
    requires = ("plan",)
    description = "Page specs pages/pNN.json from prompts.txt, tags.json and starts.json."

    def preflight(self, ctx: Context) -> list[str]:
        return [f"{n} is missing" for n in ("prompts.txt", "tags.json", "starts.json") if not (ctx.workspace.dir / n).exists()]

    def run(self, ctx: Context) -> Result:
        ws = ctx.workspace
        source = resolve(ws, ctx.books_dir or ws.root.parent)
        text = source.text()
        order = [f"{p}.{k}" for p, k in text.order]
        last = [x for x in order if x.startswith(f"{source.last}.")][-1] if source.last else order[-1]
        prompts = [line.strip() for line in (ws.read_text("prompts.txt") or "").splitlines()]
        pages = build_pages(prompts, ws.read_json("starts.json"), ws.read_json("tags.json"), order, last, source.book_ref, source.chapter)
        if ctx.dry_run:
            return Result.success(f"would write {len(pages)} page specs for {len(prompts)} panels", planned=len(pages))
        for name, spec in pages.items():
            ws.write_text(f"pages/{name}.json", json.dumps(spec, ensure_ascii=False, indent=1))
        return Result.success(f"{len(pages)} pages, {len(prompts)} panels", pages=len(pages), panels=len(prompts))
