# sutur-pipeline

Task framework for the Sutur manga pipeline (Arabic classics drawn as manga volumes on a GPU server).
Each kind of process is a **task** with a typed contract; a **runner** executes the chosen tasks for one volume in dependency order.

MIT, like the rest of the repository. Python 3.12+. Pillow (built with Raqm for the Arabic lettering) is the only dependency; everything else is the standard library.

```
sutur-pipeline tasks                              # list the stages
sutur-pipeline --root ../comic status 3 1          # what exists for book 3, volume 1
sutur-pipeline --root ../comic run 3 1 make --dry-run
GPU_URLS=http://localhost:8000,http://localhost:8001 VL_URL=http://localhost:8200 \
  sutur-pipeline --root comic run 3 1 make --slug the-harafish-1
TTS_URL=http://localhost:8300 TTS_VOICE=<voice> sutur-pipeline --root comic run 3 1 narrate --voice <voice> --speed 0.95
```

It reads and writes the same folder layout as the existing `tools/` scripts (`comic/book<N>/v<V>/pages/pNN.json`, `pNN/<panel>-s<seed>.png`, `stats.json`, ...),
so the old and new tools can work on one volume. Run it from the machine that has the GPU servers, as before.

## Tasks (stages)

`transform` tasks make files; `review` tasks look at output with a model and fix it. Order of a full volume:
`chunk -> plan -> spec -> draw -> textscan -> vision -> build -> cast -> cover -> lab -> pdf -> publish` (`make` = spec through pdf).

| Task | Kind | Does | Needs |
|---|---|---|---|
| `chunk` | transform | cuts the volume text into panel-sized pieces: `starts.json`, `chunks.txt` | book json |
| `plan` | review | the LLM writes cast, tags, cover scene and one drawing prompt per panel; never overwrites existing files; fetches an existing cover from the site | text LLM |
| `spec` | transform | page specs `pages/pNN.json` (layouts, text ranges, seeds, cleaned prompts) | plan files |
| `draw` | transform | draws the missing pictures (panels x seeds) over every image server; atomic, safe to rerun | image servers |
| `textscan` | review | tesseract finds drawn English words; flagged pictures are rejected and redrawn (5 rounds) | tesseract |
| `vision` | review | a vision model flags nudity, drawn text, bad hands...; flagged pictures are redrawn; ends with a text scan | vision server |
| `build` | transform | pages `pNN.png` with lettered captions + review sheets | fonts with Raqm |
| `cast` | transform | portraits per character + `cast.png` | image servers |
| `cover` | transform | cover candidates + `cover-final.png` (kept when it exists) | image servers |
| `lab` | transform | the behind-the-scenes page `lab.png` | site fonts |
| `pdf` | transform | `vol<N>.pdf` from cover, lab, cast and built pages | built pages |
| `narrate` | transform | speaks every captioned panel into `audio/<page>/<panel>.mp3` | speech server |
| `publish` | transform | **guarded** (`--yes`): package, copy to the production host over your ssh agent, run the remote publisher | `ssh -A` |

All of `build`, `cast`, `cover` and `lab` were checked to produce **pixel-identical** images to the old `tools/` scripts on a finished Harafish volume (see `docs/ARCHITECTURE.md`).
Speech engine notes: [docs/TTS.md](docs/TTS.md). Not ported (legacy, other chapter formats): the balloon lettering of `letter_overlay.py`, the OCR page letterer `letter_page.py`, `review_sheet.py`, `respec.py`.

## Settings (environment only, never files)

`GPU_URLS` (comma separated) or `GPU_URL`, `LLM_URL`, `LLM_MODEL`, `SITE_URL`, `FONT_DIR`, `LETTER_FONT`, `SITE_DIR`, `VL_URL`, `VL_MODEL`, `DRAW_MODEL_ID`, `DRAW_STEPS`, `DRAW_THREADS`, `VL_THREADS`, `SCAN_ROUNDS`, `TTS_URL`, `TTS_MODEL`, `TTS_VOICE`, `TTS_SPEED`, `TTS_THREADS`, `UNSLOTH_API_KEY`.
Keys are never printed (hidden from `repr`).

## Develop

```
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
PYTHONPATH=src:. python -m unittest discover -s tests -t .      # no GPU needed: the servers are faked
```

## Layout

```
src/sutur_pipeline/
  config.py        Settings.from_env
  models.py        PageSpec (wraps the json, keeps unknown keys), PictureRef, VolumeRef, write_atomic
  layout.py        page geometry: panel boxes, draw sizes
  workspace.py     folder layout of a volume
  clients/         JsonHttp (retries), ImageClient / VisionClient protocols and OpenAI-compatible implementations
  tasks/          base (Task, Context, Result), registry, draw, scan, pdf
  pipeline/        graph (ordering), runner (execution, stats), stats (stats.json)
  cli.py
tests/             fakes for the model servers; rules, graph, http, tasks
```
