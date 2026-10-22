"""Chunk task: cut the volume's text into panel-sized pieces (about 28 words, cut at clause ends, preferably at paragraph ends).

Writes `starts.json` (the clause id each panel starts at) and `chunks.txt` (one `[n] <first clause id> <text>` line per panel, what the plan task reads)."""

from __future__ import annotations

from ..source import BookText
from ..volume import VolumeSource, resolve
from .base import Context, Kind, Result, Task
from .registry import register

Clause = tuple[str, str]   # (id "paragraph.index", text without diacritics)


def panel_words(source: VolumeSource, text: BookText) -> int:
    """About 200 panels per volume: longer texts get more words per panel (28 to 60)."""
    words = sum(len(t.split()) for p, cs in enumerate(text.plain_clauses) for t in cs if source.in_range(p + 1))
    return max(28, min(60, round(words / 200)))


def clause_sequence(source: VolumeSource, text: BookText) -> list[Clause]:
    return [(f"{p + 1}.{k}", t) for p, cs in enumerate(text.plain_clauses) for k, t in enumerate(cs) if source.in_range(p + 1)]


def cut_panels(seq: list[Clause], words_per_panel: int = 28) -> list[list[Clause]]:
    """Greedy cut: a panel closes at a paragraph end after about 20 words, at a sentence end after about 26, or at 38 at the latest.

    All three limits scale with words_per_panel / 28."""
    k = words_per_panel / 28
    panels: list[list[Clause]] = []
    cur: list[Clause] = []
    words = 0
    for i, (cid, c) in enumerate(seq):
        cur.append((cid, c))
        words += len(c.split())
        last_in_para = i + 1 == len(seq) or seq[i + 1][0].endswith(".0")
        if (words >= 20 * k and last_in_para) or words >= 38 * k or (words >= 26 * k and c.rstrip().endswith((".", "؟", "!", "»"))):
            panels.append(cur)
            cur, words = [], 0
    if cur and panels:
        panels[-1].extend(cur)
    elif cur:
        panels.append(cur)
    return panels


@register
class ChunkTask(Task):
    name = "chunk"
    kind = Kind.TRANSFORM
    description = "Cut the volume's text into panel-sized pieces: starts.json and chunks.txt."

    def run(self, ctx: Context) -> Result:
        books = ctx.books_dir or ctx.workspace.root.parent
        source = resolve(ctx.workspace, books, write_merged=not ctx.dry_run)
        text = source.text()
        words = int(ctx.options["panel_words"]) if "panel_words" in ctx.options else panel_words(source, text)
        panels = cut_panels(clause_sequence(source, text), words)
        if ctx.dry_run:
            return Result.success(f"would cut {len(panels)} panels of about {words} words", planned=len(panels))
        ctx.workspace.write_json("starts.json", [p[0][0] for p in panels])
        ctx.workspace.write_text("chunks.txt", "".join(f"[{n}] {p[0][0]} " + " ".join(c for _, c in p) + "\n" for n, p in enumerate(panels)))
        return Result.success(f"{len(panels)} panels of about {words} words", panels=len(panels), words_per_panel=words)
