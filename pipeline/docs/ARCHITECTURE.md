# Architecture

## Why tasks

The old pipeline is 68 scripts glued by `volume_run.py`. Each script re-reads the folder layout, prints its own progress, and some call each other through
`subprocess`. That works, but a failure in the middle is hard to resume, nothing can be tested without a GPU, and a new stage means another script plus an
edit in the glue. The framework keeps the stages and the folder layout and changes how they are described and run.

## The contract

```python
class Task(ABC):
    name: str                      # the stage name on the command line
    kind: Kind                     # TRANSFORM or REVIEW
    requires: tuple[str, ...]      # stages that come before it (ordering; pulled in only with --with-deps)
    def preflight(self, ctx) -> list[str]     # what is missing; empty = go
    def run(self, ctx) -> Result              # OK / FAILED / SKIPPED + summary + data
```

* **Transform** tasks transform files (draw, pdf, later build, cover, lab). Given the same inputs and models they produce the same outputs, and they are idempotent: a rerun does only what is missing.
* **Review** tasks look at a transform task's output with a model and put things right. `scan` is one: it flags pictures with a vision model, rejects them, reseeds the
  panel, makes the prompt safer and calls the `draw` task through `ctx.task("draw")` until nothing is flagged or the rounds run out. A review task never knows how its transform task draws.

`Context` hands a task the volume `Workspace`, `Settings`, the model clients (behind small protocols) and the registry. Tasks never read the environment or open sockets themselves,
which is what lets the tests run them against fakes.

## Execution

`order()` sorts the chosen stages by `requires` (cycles and unknown names are errors). `Runner.run()` calls `preflight`, then `run`, times each stage, writes `stageSeconds`
to `stats.json` (same keys as before), and stops at the first FAILED result. SKIPPED means nothing to do; a review task that leaves pictures it could not fix returns OK with
`data["unresolved"]` and says so in the summary: a human review is the next step, not a crash.

## Design decisions

* Pillow is the only dependency (pictures, lettering, pdf); everything else is the standard library. No framework to learn, nothing to install on the GPU box beyond Python 3.12 and Pillow.
* The JSON on disk stays the source of truth. `PageSpec` wraps the dict so keys the framework does not know survive a save; all writes are atomic (temp file + rename).
* Transport errors are `TransportError` after retries with backoff (5xx/429/timeouts retried, 4xx not). A failed picture fails the stage but keeps the others, and a rerun finishes the rest.
* Secrets only from the environment; clients hide keys from `repr`.
* Publishing stays outside the default flow on purpose: it will be a task that refuses to run without an explicit `--yes`, and never runs as part of `--with-deps`.

## Migration map (from `tools/`)

| Old script | Is now | Check |
|---|---|---|
| `harafish_chunk.py`, `volctx.py`, `page_text.py` | `chunk`, `volume.py`, `source.py` | panel list identical on Harafish v1 (219 panels) |
| `prompts_llm.py` (+ `prompt_rules.txt`) | `plan`, `prompts.py`, `resources/prompt_rules.txt` | prompt texts copied verbatim; cleaning rules unit-tested |
| `harafish_spec.py` | `spec` | page counts match the finished volume (105 panels -> 18 pages); short volumes get evenly filled pages (the old script could not) |
| `panel_page.py draw`, `volume_run.draw_all` | `draw` | |
| `text_scan.py`, `volume_run.st_scan` | `textscan` | shared review loop with `vision` |
| `vision_scan.py`, `volume_run.st_vision` | `vision` | |
| `harafish_build.py`, `panel_page.build`, `letter_overlay.py` (fonts, wrap) | `build`, `render/page.py`, `render/text.py` | **pixel-identical** pages p01, p05, p09, p14, p18 |
| `cast_vol.py` | `cast`, `render/cast.py` | pixel-identical cast page |
| `cover_draw.py`, `cover_vol.py` | `cover`, `render/cover.py` | pixel-identical cover |
| `lab_page.py` | `lab`, `render/lab.py` | pixel-identical lab page |
| `vol_pdf.py`, `make_pdf.py` | `pdf` | |
| `publish_volume.py`, `publish_remote.py` | `publish`, `publishing.py`, `resources/publish_remote.py` | package and commands unit-tested with a fake transport; **never run against the live site** |

Not ported: the balloon/webtoon lettering (`letter_overlay.py` balloons, `letter_page.py`), `review_sheet.py`, `respec.py`: they belong to the older chapter formats.

Real-data comparison with the old pipeline (2026-10-23, GPU box, book 19 "Rue Morgue" volume 1 restored from the backup):

* page specs: 10 of 10 identical to the old ones apart from the seeds the scan tasks changed;
* built pages: 10 of 10 pixel-identical (same pictures, new `build`); cast page pixel-identical once the old `cast_picks` are used; lab page identical; PDF 13 pages = 13.
* pictures cannot be compared pixel for pixel: the two Z-Image server copies give the same picture for a seed only within one copy, so a redraw never reproduces an old picture (a property of the servers, not the pipeline).
* a fresh volume (book 76 "Olya", 64 panels, 11 pages, 192 pictures) ran `chunk plan spec draw textscan vision build cast cover lab pdf` on the GPU box in about 5.5 minutes.
* faults found this way and fixed: the cast came out empty when the LLM wrote roles in English (roles are now translated, a character is no longer dropped for it); the review report said "still flagged" for pictures that had just been redrawn (a final judge-only pass now reports the truth); the default negative prompt had lost the old ship words.

What is verified and what is not: every image task matches the old tools on real volumes; the full chain runs on a tiny volume against fake model servers (`tests/test_end_to_end.py`).
Not verified: a full real volume end to end on the GPU box (needs the draw and vision servers restored), `plan` against the real Qwen model, `publish` against the site.

## Next steps

1. Run a real volume through `make` on the GPU box and compare with the old `volume_run.py` output; then retire `volume_run.py` and `tools/gpu.sh run`.
2. A `SourceText` service replacing `volctx.py` (also feeds the site's text mode: `tools/export_texts.py` is the same logic).
3. Resumable runs: a `run.json` per volume with each stage's inputs hash, to skip stages whose inputs did not change.
4. Event stream (JSON lines) for the GPU dashboard instead of printed lines.
