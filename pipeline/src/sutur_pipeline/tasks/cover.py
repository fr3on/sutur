"""Cover task: cover art candidates from `cover.prompt.txt`, then the finished cover (art in black and white, title and credits drawn by code).

An existing `cover-final.png` is kept (a "coming soon" book already has its cover on the site).
`publish.json` holds the texts (`cover`: series, volume, title, author) and the chosen candidate (`cover_seed`, default 1)."""

from __future__ import annotations

from PIL import Image

from ..errors import PipelineError, SpecError
from ..layout import PAGE_H, PAGE_W
from ..models import write_atomic
from ..render.cover import compose_cover, cover_sheet
from ..render.text import require_raqm
from .base import Context, Kind, Result, Task
from .registry import register

CANDIDATE_SEEDS = (1, 2, 3, 4)


@register
class CoverTask(Task):
    name = "cover"
    kind = Kind.TRANSFORM
    requires = ("cast",)
    description = "Draw cover candidates and build cover-final.png (kept when it already exists)."

    def preflight(self, ctx: Context) -> list[str]:
        if (ctx.workspace.dir / "cover-final.png").exists():
            return []
        return [f"{n} is missing (run the plan task)" for n in ("cover.prompt.txt", "publish.json") if not (ctx.workspace.dir / n).exists()]

    def run(self, ctx: Context) -> Result:
        ws = ctx.workspace
        if (ws.dir / "cover-final.png").exists():
            return Result.skipped("cover-final.png exists (kept, e.g. the cover already on the site)")
        require_raqm()
        fonts = ctx.need_fonts("title", "body")
        prompt = (ws.read_text("cover.prompt.txt") or "").strip()
        publish = ws.read_json("publish.json")
        texts = publish.get("cover")
        if not texts or not all(k in texts for k in ("series", "volume", "title", "author")):
            raise SpecError('publish.json needs "cover": {"series", "volume", "title", "author"}')
        seed = int(publish.get("cover_seed", 1))
        missing = [s for s in CANDIDATE_SEEDS if not (ws.dir / f"cover-s{s}.png").exists()]
        if ctx.dry_run:
            return Result.success(f"would draw {len(missing)} cover candidates and build cover-final.png from seed {seed}", planned=len(missing))
        pool = ctx.need_images()
        try:
            for i, s in enumerate(missing):
                write_atomic(ws.dir / f"cover-s{s}.png", pool.for_job(i).generate(prompt, PAGE_W, PAGE_H, s))
        except PipelineError as exc:
            return Result.failure(f"cover candidate failed: {exc}")
        cover_sheet([Image.open(ws.dir / f"cover-s{s}.png") for s in CANDIDATE_SEEDS]).save(ws.dir / "cover-review.jpg", quality=82)
        art = ws.dir / f"cover-s{seed}.png"
        if not art.exists():
            raise SpecError(f"cover_seed {seed} has no picture ({art.name}); candidates are seeds {CANDIDATE_SEEDS}")
        compose_cover(Image.open(art), fonts, texts["series"], texts["volume"], texts["title"], texts["author"]).save(ws.dir / "cover-final.png")
        return Result.success(f"cover built from candidate {seed} ({len(missing)} drawn)", drawn=len(missing))
