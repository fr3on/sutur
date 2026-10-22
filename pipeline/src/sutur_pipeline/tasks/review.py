"""The review loop shared by the tasks that judge pictures (vision model, OCR): judge every picture, set the flagged ones aside, give their panels fresh
seeds (and a safer prompt when the policy says so), have the draw task redraw them, and go again until nothing is flagged or the rounds run out."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models import DEFAULT_SEEDS, PageSpec, PictureRef
from .base import Context, Result, Status


@dataclass
class Finding:
    spec: PageSpec
    panel_id: str
    picture: PictureRef
    reasons: list[str]


@dataclass
class Round:
    """What one judging pass found."""

    judged: int = 0
    unjudged: int = 0
    findings: list[Finding] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)   # task-specific numbers (the vision task counts nude panels)


Judge = Callable[[Context], Round]
Simplify = Callable[[str, Sequence[str], int], tuple[str, bool]]


def reseed(panel: dict[str, Any], on_disk: Sequence[int], rejected: set[int]) -> None:
    """Replace the rejected seeds with fresh ones, ten above anything used so far, so a redraw never reproduces a rejected picture."""
    current = list(panel.get("seeds", DEFAULT_SEEDS))
    top = max([*current, *on_disk, *rejected])
    panel["seeds"] = [s for s in current if s not in rejected] + [top + 10 + i for i in range(len(rejected))]


def remediate(ctx: Context, findings: list[Finding], round_no: int, simplify: Simplify) -> None:
    """Reject the flagged pictures (moved to bad/, never deleted), reseed their panels, adjust their prompts, save the specs."""
    by_panel: dict[tuple[str, str], list[Finding]] = {}
    for f in findings:
        by_panel.setdefault((f.spec.name, f.panel_id), []).append(f)
    touched: dict[str, PageSpec] = {}
    for items in by_panel.values():
        spec = items[0].spec
        panel = spec.panel(items[0].panel_id)
        on_disk = [p.seed for p in ctx.workspace.pictures(spec, panel["id"])]
        rejected = {f.picture.seed for f in items}
        for f in items:
            ctx.workspace.reject(f.picture)
        panel["prompt"], plain = simplify(panel["prompt"], [r for f in items for r in f.reasons], round_no)
        if plain:
            panel["plain"] = True
        reseed(panel, on_disk, rejected)
        touched[spec.name] = spec
    for spec in touched.values():
        spec.save()


def run_loop(ctx: Context, judge: Judge, rounds: int, simplify: Simplify, label: str) -> tuple[Result, Round]:
    """Judge, remediate, redraw, repeat. Returns the result and the last round (so a task can add its own numbers)."""
    redrawn = 0
    last = Round()
    for round_no in range(1, rounds + 2):   # `rounds` passes of judge + redraw, then one last judge-only pass so the report is true
        last = judge(ctx)
        ctx.log.info("%s round %d: %d judged, %d unjudged, %d flagged", label, round_no, last.judged, last.unjudged, len(last.findings))
        if last.judged == 0 and last.unjudged:
            return Result.failure(f"{label}: no usable answer for any picture"), last
        if not last.findings or ctx.dry_run or round_no > rounds:
            break
        remediate(ctx, last.findings, round_no, simplify)
        redrawn += len(last.findings)
        drawn = ctx.task("draw").run(ctx)
        if not drawn.ok:
            return Result.failure(f"redraw failed: {drawn.summary}", redrawn=redrawn), last
    left = [f"{f.spec.name}/{f.picture.path.name}: {', '.join(f.reasons)}" for f in last.findings]
    data = {"redrawn": redrawn, "unresolved": left, **last.extra}
    if left and not ctx.dry_run:
        return Result(Status.OK, f"{len(left)} pictures still flagged after {rounds} rounds, review them by hand", data), last
    summary = f"{len(left)} flagged" if left else f"clean: {last.judged} pictures judged, {redrawn} redrawn"
    return Result.success(summary, **data), last
