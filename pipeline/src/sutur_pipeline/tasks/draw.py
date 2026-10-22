"""Draw task: one picture per panel and seed, spread over every image server."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..errors import PipelineError
from ..layout import draw_size
from ..models import PageSpec, write_atomic
from .base import Context, Kind, Result, Task
from .registry import register


@dataclass(frozen=True)
class DrawJob:
    """One picture to draw. Pictures that already exist are never in the list, so a rerun only does what is missing."""

    target: Path
    prompt: str
    width: int
    height: int
    seed: int


def plan_jobs(spec: PageSpec) -> list[DrawJob]:
    """Every missing `<panel>-s<seed>.png` of a page, in reading order."""
    boxes = spec.boxes()
    jobs: list[DrawJob] = []
    for panel in spec.panels():
        width, height = draw_size(boxes[panel["id"]])
        for seed in spec.seeds_for(panel):
            target = spec.pictures_dir / f"{panel['id']}-s{seed}.png"
            if not (target.exists() and target.stat().st_size > 0):
                jobs.append(DrawJob(target, spec.full_prompt(panel), width, height, seed))
    return jobs


@register
class DrawTask(Task):
    name = "draw"
    kind = Kind.TRANSFORM
    requires = ("spec",)
    description = "Draw the missing pictures of every page (panels x seeds) on the image servers."

    def preflight(self, ctx: Context) -> list[str]:
        return [] if ctx.workspace.page_specs() else [f"no page specs in {ctx.workspace.pages_dir}"]

    def run(self, ctx: Context) -> Result:
        jobs = [j for spec in ctx.workspace.page_specs() for j in plan_jobs(spec)]
        if not jobs:
            return Result.skipped("nothing to draw: every picture exists")
        if ctx.dry_run:
            return Result.success(f"would draw {len(jobs)} pictures", planned=len(jobs))
        pool = ctx.need_images()

        def one(item: tuple[int, DrawJob]) -> str | None:
            index, job = item
            try:
                write_atomic(job.target, pool.for_job(index).generate(job.prompt, job.width, job.height, job.seed))
            except PipelineError as exc:
                return f"{job.target.name}: {exc}"
            ctx.log.info("drew %s %dx%d", job.target.name, job.width, job.height)
            return None

        with ThreadPoolExecutor(ctx.settings.draw_threads_per_server * len(pool)) as ex:
            errors = [e for e in ex.map(one, enumerate(jobs)) if e]
        drawn = len(jobs) - len(errors)
        if errors:
            return Result.failure(f"drew {drawn} of {len(jobs)} pictures; {len(errors)} failed (first: {errors[0]})", drawn=drawn, errors=errors)
        return Result.success(f"drew {drawn} pictures", drawn=drawn)
