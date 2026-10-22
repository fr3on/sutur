"""Cast task: one portrait per character (image servers), then the characters page `cast.png`.

The portraits used are the ones picked in publish.json (`cast_picks`, default seed 1)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..errors import PipelineError
from ..models import write_atomic
from ..render.cast import compose_cast_page
from ..render.text import require_raqm
from .base import Context, Kind, Result, Task
from .registry import register

PORTRAIT_SIZE = 768
SUFFIX = " No text, no letters, no border, no color."


@register
class CastTask(Task):
    name = "cast"
    kind = Kind.TRANSFORM
    requires = ("build",)
    description = "Draw one portrait per character (cast.json) and build the characters page cast.png."

    def preflight(self, ctx: Context) -> list[str]:
        return [] if (ctx.workspace.dir / "cast.json").exists() else ["cast.json is missing (run the plan task)"]

    def run(self, ctx: Context) -> Result:
        require_raqm()
        ws = ctx.workspace
        fonts = ctx.need_fonts("title", "body")
        cast = ws.read_json("cast.json")
        seeds = [int(s) for s in ctx.options.get("cast_seeds", "1,2").split(",")]
        jobs = [(cid, seed, cast["prefix"] + prompt + SUFFIX) for cid, _name, _role, prompt in cast["cast"] for seed in seeds
                if not (ws.dir / "cast" / f"{cid}-s{seed}.png").exists()]
        if ctx.dry_run:
            return Result.success(f"would draw {len(jobs)} portraits and build cast.png", planned=len(jobs))
        errors: list[str] = []
        if jobs:
            pool = ctx.need_images()

            def one(item: tuple[int, tuple[str, int, str]]) -> str | None:
                index, (cid, seed, prompt) = item
                try:
                    png = pool.for_job(index).generate(prompt, PORTRAIT_SIZE, PORTRAIT_SIZE, seed)
                except PipelineError as exc:
                    return f"{cid}-s{seed}: {exc}"
                write_atomic(ws.dir / "cast" / f"{cid}-s{seed}.png", png)
                return None

            with ThreadPoolExecutor(ctx.settings.draw_threads_per_server * len(pool)) as ex:
                errors = [e for e in ex.map(one, enumerate(jobs)) if e]
        if errors:
            return Result.failure(f"{len(errors)} of {len(jobs)} portraits failed (first: {errors[0]})", errors=errors)
        picks = {k: int(v) for k, v in (ws.read_json("publish.json", {}) or {}).get("cast_picks", {}).items()}
        image = compose_cast_page(cast["cast"], ws.dir / "cast", picks, fonts)
        image.save(ws.dir / "cast.png")
        return Result.success(f"{len(jobs)} portraits drawn, cast.png built for {len(cast['cast'])} characters", drawn=len(jobs))
