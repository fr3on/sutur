"""Build task: assemble every page from the drawn panels (picks per panel, captions lettered in code) and write the review contact sheets.

Per panel the first seed (in the spec's order) whose picture has no solid black side bars; overrides in `picks.json` ({"p06": {"e": 12}}).
Writes `pages/pNN.png` and `review/sheet-K.jpg` (six pages per sheet). `--pages 01,02` (option `pages`) builds only those."""

from __future__ import annotations

from ..render.page import choose_picks, compose_page, contact_sheets
from ..render.text import require_raqm
from ..source import BookText, find_book_file
from .base import Context, Kind, Result, Task
from .registry import register


@register
class BuildTask(Task):
    name = "build"
    kind = Kind.TRANSFORM
    requires = ("vision",)
    description = "Assemble pages/pNN.png from the drawn panels with lettered captions, plus review/sheet-K.jpg."

    def preflight(self, ctx: Context) -> list[str]:
        specs = ctx.workspace.page_specs()
        if not specs:
            return [f"no page specs in {ctx.workspace.pages_dir}"]
        return [] if any(ctx.workspace.pictures(s) for s in specs) else ["no drawn pictures yet (run the draw task)"]

    def run(self, ctx: Context) -> Result:
        require_raqm()
        fonts = ctx.need_fonts("caption")
        ws = ctx.workspace
        only = {x.strip() for x in ctx.options.get("pages", "").split(",") if x.strip()}
        specs = [s for s in ws.page_specs() if not only or s.name[1:] in only]
        if ctx.dry_run:
            return Result.success(f"would build {len(specs)} pages", planned=len(specs))
        overrides = ws.read_json("picks.json", {})
        books = (ctx.books_dir or ws.root.parent, ws.root.parent)
        texts: dict[tuple[str, int], BookText] = {}
        oversize: list[str] = []
        for spec in specs:
            key = (spec.data["book"], int(spec.data.get("chapter", 2)))
            if key not in texts:
                texts[key] = BookText.from_file(find_book_file(key[0], *books), key[1])
            result = compose_page(spec, choose_picks(spec, overrides.get(spec.name)), texts[key], fonts)
            result.image.save(ws.pages_dir / f"{spec.name}.png")
            oversize += [f"{spec.name}/{pid}" for pid in result.omitted]
        built = ws.built_pages()
        (ws.dir / "review").mkdir(exist_ok=True)
        sheets = contact_sheets(built)
        for n, sheet in enumerate(sheets, start=1):
            sheet.save(ws.dir / "review" / f"sheet-{n}.jpg", quality=82)
        note = f"; captions that needed an oversize strip: {', '.join(oversize)}" if oversize else ""
        summary = f"built {len(specs)} pages ({len(built)} in the volume), {len(sheets)} review sheets{note}"
        return Result.success(summary, built=len(specs), sheets=len(sheets), oversize=oversize)
