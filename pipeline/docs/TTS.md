# Speech (narrate task)

`narrate` speaks every lettered panel's caption into `audio/<page>/<panel>.mp3` through any server that offers `POST /v1/audio/speech`
(see `servers/silma_server.py` for the one we run). Settings: `TTS_URL`, `TTS_VOICE`, `TTS_SPEED`, `TTS_MODEL`, `TTS_THREADS`; `--voice` and `--speed` override per run.

## The engine we tested: SILMA TTS (Apache-2.0 weights, MIT code)

Tested 2026-10-22 on a GH200 (aarch64, Ubuntu 22.04, CUDA 13, torch 2.14):

* `uv venv --python 3.12`, `uv pip install --no-deps silma-tts` then its other requirements. `nemo-text-processing` cannot be installed because its dependency `pynini` does not build here;
  silma only uses it to spell out digits, so a pass-through `Normalizer` stand-in was placed in site-packages. Digits in captions are therefore not read as words (a micromamba/conda-forge `pynini` would fix that).
* Load 16 s, then about 0.5 s of compute per caption. 17 panels of Harafish v1 took 29 s end to end through the pipeline.
* SILMA keeps the book's diacritics when the text has three or more marks; below that it runs its own diacritizer (CATT) and *replaces* the text with its guess. A lightly marked caption can therefore be
  read differently from the printed text. Check captions with few marks by ear.
* A voice is a reference recording under 8 s plus its transcript. The `default` voice is a sample bundled with silma-tts and its recording rights are not documented: **tests only**.
  Production needs a voice we have the right to use (a consenting speaker).
* Not tested: audio quality by a native listener, long-running stability, concurrency (the server serialises requests).
