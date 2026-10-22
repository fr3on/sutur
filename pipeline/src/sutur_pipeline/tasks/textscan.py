"""Text scan task (a review): tesseract finds drawn English words (the model sometimes draws speech bubbles or signs); flagged pictures are redrawn.

A panel that keeps failing gets a shorter, plainer prompt from the third round on. Needs `tesseract` on the machine (apt-get install tesseract-ocr)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..errors import PipelineError
from ..models import PictureRef
from .base import Context, Kind, Result, Task
from .registry import register
from .review import Finding, Round, run_loop

WORD = re.compile(r"[A-Za-z]{3,}")
ROUNDS = 5


def words_from_tsv(tsv: str, min_conf: float) -> list[str]:
    """English words tesseract is sure about: 3+ letters with a vowel, confidence >= min_conf, and at least 4 letters in all."""
    words = []
    for line in tsv.splitlines():
        c = line.split("\t")
        if len(c) >= 12 and c[11].strip() and WORD.fullmatch(c[11].strip()) and float(c[10]) >= min_conf and re.search(r"[aeiouAEIOU]", c[11]):
            words.append(c[11].strip())
    return words if sum(len(w) for w in words) >= 4 else []


def has_text(path: Path, min_conf: float = 60.0) -> list[str]:
    """English words in a picture, read as drawn and upscaled (an italic bubble may be read by only one of the two)."""
    from PIL import Image

    out = ""
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        im = Image.open(path).convert("L")
        im.resize((int(im.width * 1.5), int(im.height * 1.5))).save(tmp.name)
        for src in (str(path), tmp.name):
            cmd = ["tesseract", src, "-", "--psm", "11", "-l", "eng", "tsv"]
            run = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "OMP_THREAD_LIMIT": "1"}, check=False)
            out += "\n".join(run.stdout.splitlines()[1:]) + "\n"
    return words_from_tsv(out, min_conf)


def simplify(prompt: str, reasons: Sequence[str], round_no: int) -> tuple[str, bool]:
    """Unchanged for two rounds; from the third the first sentence only (at most 140 characters), marked plain."""
    if round_no >= 3:
        return re.split(r"[.;]", prompt)[0][:140], True
    return prompt, False


@register
class TextScanTask(Task):
    name = "textscan"
    kind = Kind.REVIEW
    requires = ("draw",)
    description = "Tesseract finds pictures with drawn English words; they are rejected and redrawn (up to 5 rounds)."

    def preflight(self, ctx: Context) -> list[str]:
        problems = [] if ctx.workspace.page_specs() else [f"no page specs in {ctx.workspace.pages_dir}"]
        if not shutil.which("tesseract"):
            problems.append("tesseract is not installed (apt-get install tesseract-ocr)")
        return problems

    def run(self, ctx: Context) -> Result:
        if not shutil.which("tesseract"):   # never report "clean" because nothing could be read
            return Result.failure("tesseract is not installed (apt-get install tesseract-ocr)")
        conf = float(os.environ.get("TEXT_CONF", "60"))

        def review(c: Context) -> Round:
            jobs: list[tuple[object, PictureRef]] = [(spec, p) for spec in c.workspace.page_specs() for p in c.workspace.pictures(spec)]

            def one(job: tuple[object, PictureRef]) -> list[str]:
                try:
                    return has_text(job[1].path, conf)
                except (OSError, PipelineError):
                    return []

            with ThreadPoolExecutor(c.settings.scan_threads) as ex:
                found = list(ex.map(one, jobs))
            rd = Round(judged=len(jobs))
            for (spec, pic), words in zip(jobs, found, strict=True):
                if words:
                    rd.findings.append(Finding(spec, pic.panel, pic, [f"drawn text: {', '.join(words[:3])}"]))  # type: ignore[arg-type]
            return rd

        return run_loop(ctx, review, ROUNDS, simplify, "textscan")[0]
