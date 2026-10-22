"""PDF task: cover, lab page, cast page, then the built pages, 864x1440 px each (432x720 pt in the PDF)."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from ..layout import PAGE_H, PAGE_W
from ..models import write_atomic
from .base import Context, Kind, Result, Task
from .registry import register

OPTIONAL = ("lab.png", "cast.png")   # skipped when missing


def pdf_inputs(volume_dir: Path, built: list[Path]) -> list[Path]:
    """Files in reading order: cover-final.png, the optional front pages that exist, then the built pages."""
    front = [volume_dir / n for n in OPTIONAL if (volume_dir / n).exists()]
    return [volume_dir / "cover-final.png", *front, *built]


@register
class PdfTask(Task):
    name = "pdf"
    kind = Kind.TRANSFORM
    requires = ("build", "cover", "lab")
    description = "Assemble vol<N>.pdf from the cover, lab page, cast page and the built pages."

    def preflight(self, ctx: Context) -> list[str]:
        problems = []
        if not (ctx.workspace.dir / "cover-final.png").exists():
            problems.append("cover-final.png is missing (run the cover stage)")
        if not ctx.workspace.built_pages():
            problems.append("no built pages (pages/pNN.png): run the build stage")
        return problems

    def run(self, ctx: Context) -> Result:
        files = pdf_inputs(ctx.workspace.dir, ctx.workspace.built_pages())
        out = ctx.workspace.dir / f"vol{ctx.workspace.ref.volume}.pdf"
        if ctx.dry_run:
            return Result.success(f"would write {out.name} with {len(files)} pages", planned=len(files))
        images = []
        for f in files:
            im = Image.open(f).convert("RGB")
            if f.parent.name == "pages" and im.size != (PAGE_W, PAGE_H):
                im = im.resize((PAGE_W, PAGE_H), Image.Resampling.LANCZOS)   # built pages only; the cover keeps its own size
            images.append(im)
        buf = io.BytesIO()
        images[0].save(buf, "PDF", save_all=True, append_images=images[1:], resolution=144.0)
        write_atomic(out, buf.getvalue())
        return Result.success(f"wrote {out.name}: {len(images)} pages", path=str(out), pages=len(images))
