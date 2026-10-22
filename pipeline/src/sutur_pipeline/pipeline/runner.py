"""The runner: executes the ordered stages for one volume, stops at the first failure, keeps the stats."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from ..errors import PipelineError
from ..tasks.base import Context, Result, Status
from ..tasks.registry import Registry
from .graph import order
from .stats import record_stage


@dataclass
class StageOutcome:
    stage: str
    result: Result
    seconds: float


@dataclass
class RunReport:
    outcomes: list[StageOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(o.result.ok for o in self.outcomes)

    @property
    def failed(self) -> StageOutcome | None:
        return next((o for o in self.outcomes if not o.result.ok), None)


def _say_now(message: str) -> None:
    """Progress lines go out at once, so a run in the background (nohup, a pipe) can be followed."""
    print(message, flush=True)


class Runner:
    def __init__(self, registry: Registry, on_event: Callable[[str], None] = _say_now) -> None:
        self.registry, self._say = registry, on_event

    def run(self, ctx: Context, stages: Iterable[str], with_deps: bool = False) -> RunReport:
        ctx.registry = self.registry
        plan = order(stages, self.registry, with_deps)
        report = RunReport()
        for name in plan:
            task = self.registry.get(name)
            self._say(f"== {name}  ({task.kind.value})")
            problems = task.preflight(ctx)
            if problems:
                result = Result.failure("; ".join(problems))
                report.outcomes.append(StageOutcome(name, result, 0.0))
                self._say(f"   cannot start: {result.summary}")
                break
            started = time.monotonic()
            try:
                result = task.run(ctx)
            except PipelineError as exc:
                result = Result.failure(str(exc))
            seconds = time.monotonic() - started
            report.outcomes.append(StageOutcome(name, result, seconds))
            self._say(f"   {result.status.value}: {result.summary}  [{seconds:.1f}s]")
            if result.status is Status.OK and not ctx.dry_run:
                record_stage(ctx.workspace, name, seconds)
            if not result.ok:
                break
        return report
