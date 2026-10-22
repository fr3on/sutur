"""Lab task: the Sutur "behind the scenes" page right after the cover, `lab.png`."""

from __future__ import annotations

from ..render.lab import compose_lab_page
from ..render.text import require_raqm
from .base import Context, Kind, Result, Task
from .registry import register


@register
class LabTask(Task):
    name = "lab"
    kind = Kind.TRANSFORM
    requires = ("cover",)
    description = "Write lab.png, the behind-the-scenes page."

    def run(self, ctx: Context) -> Result:
        require_raqm()
        fonts = ctx.need_fonts("latin", "vazir_bold", "vazir_regular")
        if ctx.dry_run:
            return Result.success("would write lab.png")
        compose_lab_page(fonts).save(ctx.workspace.dir / "lab.png")
        return Result.success("lab.png written")
