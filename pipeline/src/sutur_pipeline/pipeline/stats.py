"""Per-volume run statistics in `stats.json`, the same file and keys the existing tools write (the site's "making of" numbers read it)."""

from __future__ import annotations

import time

from ..workspace import Workspace


def record_stage(ws: Workspace, stage: str, seconds: float) -> None:
    """Add a stage's wall time to `stageSeconds` (it accumulates over reruns) and stamp `builtAt` when the pdf stage finishes."""
    stats = ws.read_json("stats.json", {}) or {}
    seconds_by_stage = stats.setdefault("stageSeconds", {})
    seconds_by_stage[stage] = round(seconds_by_stage.get(stage, 0) + seconds)
    if stage == "pdf":
        stats["builtAt"] = int(time.time())
    ws.write_json("stats.json", stats)
