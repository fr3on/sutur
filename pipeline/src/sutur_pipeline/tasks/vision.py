"""Vision task (a review): a vision model looks at every drawn picture and flags what a reviewer would reject; flagged ones are set aside and redrawn.

A 7B vision model is a filter, not a guarantee: the review sheet still gets a human look. Plain, non-explicit nudity is allowed where the story has it
(the book is then rated 18+ at publish time); everything else on the list is redrawn. When the loop ends the text scan runs once more."""

from __future__ import annotations

import io
import json
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from ..clients import VisionClient
from ..errors import PipelineError
from ..models import PictureRef
from .base import Context, Kind, Result, Task
from .registry import register
from .review import Finding, Round, run_loop

FIELDS = ("nudity", "explicit", "minor_nude", "text", "animal_as_person", "modern_object", "bad_hands", "cage")
REDRAW = tuple(f for f in FIELDS if f != "nudity")   # nudity alone is kept and counted
REVEALING = ("nudity", "explicit", "minor_nude")
COVER = "Wide shot, the figure seen from behind or in profile at a distance, long hair, steam and cloth covering the body, nothing revealing."
PLAIN_FALLBACK = "Wide calm view of the room, fully clothed people in long robes standing and looking on, "

QUESTION = """This is one panel of a black-and-white manga set in the medieval Islamic Middle East. Answer with JSON only, true or false for each field, and say true ONLY when it is clearly visible:
"nudity": a naked or undressed adult figure, even if non-explicit (seen from behind, in steam, partly covered).
"explicit": nipples, breasts uncovered in front view, genitals or pubic area visible (even as simple line art), a sexual pose or act, or a sexualized focus on the body. A figure seen from behind, covered by hair, steam, water, cloth or shadow is NOT explicit.
"minor_nude": a child or young teenager without clothes.
"text": any letters, words, numbers, speech bubble, sign or banner drawn inside the picture.
"animal_as_person": an animal drawn with a human body, human clothes, or standing upright like a person, or a person with an animal's head.
"modern_object": an object from after the year 1900 (phone, car, electric lamp, glasses, wristwatch, modern clothes).
"bad_hands": hands clearly deformed, with extra or missing fingers.
"cage": an animal or fish inside a cage.
Example: {"nudity": false, "explicit": false, "minor_nude": false, "text": false, "animal_as_person": false, "modern_object": false, "bad_hands": false, "cage": false}"""


def parse_flags(answer: str) -> list[str]:
    """The fields the model said are true. Raises ValueError when the answer holds no JSON object."""
    m = re.search(r"\{.*\}", answer, re.S)
    if not m:
        raise ValueError("no JSON in the answer")
    data = json.loads(m.group(0))
    return [f for f in FIELDS if data.get(f) is True]


def to_jpeg(path: Path, longest: int = 896) -> bytes:
    im = Image.open(path).convert("RGB")
    im.thumbnail((longest, longest))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def judge(vision: VisionClient, picture: PictureRef, attempts: int = 3) -> list[str] | None:
    """Flags for one picture, or None when the model never gave a usable answer (the picture counts as unjudged, not as clean)."""
    jpeg = to_jpeg(picture.path)
    for _ in range(attempts):
        try:
            return parse_flags(vision.ask(jpeg, QUESTION))
        except (PipelineError, ValueError):
            continue
    return None


def must_redraw(flags: Sequence[str], prompt: str) -> list[str]:
    """Flags that send a picture back for a redraw. Nudity does so only once, while the prompt has no covering words yet."""
    return [f for f in flags if f in REDRAW or (f == "nudity" and COVER not in prompt)]


def simplify(prompt: str, reasons: Sequence[str], round_no: int) -> tuple[str, bool]:
    """The prompt for the next try and whether it was reduced to a plain scene (from the second round on)."""
    if round_no >= 2:
        return PLAIN_FALLBACK + re.split(r"[.;]", prompt)[0][:100], True
    if any(r in REVEALING for r in reasons) and COVER not in prompt:
        return prompt.rstrip() + " " + COVER, False
    return prompt, False


@register
class VisionTask(Task):
    name = "vision"
    kind = Kind.REVIEW
    requires = ("textscan",)
    description = "Vision-model review of every picture; flagged ones are rejected and redrawn (up to SCAN_ROUNDS rounds), then the text scan runs once more."

    def preflight(self, ctx: Context) -> list[str]:
        return [] if ctx.workspace.page_specs() else [f"no page specs in {ctx.workspace.pages_dir}"]

    def run(self, ctx: Context) -> Result:
        vision = ctx.need_vision()

        def review(c: Context) -> Round:
            jobs = [(spec, p) for spec in c.workspace.page_specs() for p in c.workspace.pictures(spec)]
            with ThreadPoolExecutor(c.settings.vision_threads) as ex:
                verdicts = list(ex.map(lambda j: judge(vision, j[1]), jobs))
            rd = Round()
            nude: set[tuple[str, str]] = set()
            for (spec, pic), flags in zip(jobs, verdicts, strict=True):
                if flags is None:
                    rd.unjudged += 1
                    continue
                rd.judged += 1
                if "nudity" in flags:
                    nude.add((spec.name, pic.panel))
                reasons = must_redraw(flags, spec.panel(pic.panel)["prompt"])
                if reasons:
                    rd.findings.append(Finding(spec, pic.panel, pic, reasons))
            rd.extra["nudity_panels"] = len(nude)
            c.workspace.write_json("mature.json", {"nudity_panels": len(nude)})   # publish rates the book 18+ when this is above 0
            return rd

        result, last = run_loop(ctx, review, ctx.settings.scan_rounds, simplify, "vision")
        if not result.ok or ctx.dry_run:
            return result
        text = ctx.task("textscan").run(ctx)   # the redraws may have brought drawn words back
        nude_panels = last.extra.get("nudity_panels", 0)
        note = f"; {nude_panels} panels with non-explicit nudity (kept, book rated 18+)" if nude_panels else ""
        return Result(result.status, f"{result.summary}{note}; text scan: {text.summary}", {**result.data, "textscan": text.data})
