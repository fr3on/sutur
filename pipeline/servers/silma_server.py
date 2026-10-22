"""OpenAI-compatible speech server around SILMA TTS (Apache-2.0 weights). Run it where the GPU is:

    TTS_VOICES_DIR=~/voices TTS_API_KEY=... uvicorn silma_server:app --host 127.0.0.1 --port 8300 --app-dir servers

POST /v1/audio/speech {"input": "...", "voice": "name", "speed": 1.0, "response_format": "mp3"} -> mp3 bytes. Not part of the pipeline package on purpose: it needs torch and
silma-tts, the pipeline core needs neither.

A voice is a reference recording: `<TTS_VOICES_DIR>/<voice>.wav` (under 8 seconds) with its transcript in `<voice>.txt` (optional; transcribed automatically when missing).
The voice `default` is the sample that ships with silma-tts: for tests only, its recording rights are not documented.
"""

from __future__ import annotations

import glob
import hmac
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

VOICES = Path(os.environ.get("TTS_VOICES_DIR", "~/voices")).expanduser()
KEY = os.environ.get("TTS_API_KEY", "")
SEED = int(os.environ.get("TTS_SEED", "1"))

app = FastAPI(title="silma-speech")
_lock = threading.Lock()   # one generation at a time: the model keeps state on the GPU
_model = None


class SpeechRequest(BaseModel):
    model: str = "silma-tts"
    input: str = Field(min_length=1, max_length=2000)
    voice: str = "default"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    response_format: str = "mp3"


def _tts():
    global _model
    if _model is None:
        from silma_tts.api import SilmaTTS

        _model = SilmaTTS()
    return _model


def _voice(name: str) -> tuple[str, str]:
    """(reference wav, its transcript or "")."""
    if name == "default":
        import site

        found = glob.glob(site.getsitepackages()[0] + "/silma_tts/infer/ref_audio_samples/ar.ref.24k.wav")
        if not found:
            raise HTTPException(500, "the bundled sample voice is missing")
        return found[0], ""
    if not name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "bad voice name")
    wav = VOICES / f"{name}.wav"
    if not wav.is_file():
        raise HTTPException(404, f"no voice {name!r} in {VOICES}")
    txt = VOICES / f"{name}.txt"
    return str(wav), txt.read_text(encoding="utf-8").strip() if txt.is_file() else ""


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "voices": sorted(p.stem for p in VOICES.glob("*.wav")) if VOICES.is_dir() else [], "loaded": _model is not None}


@app.post("/v1/audio/speech")
def speech(req: SpeechRequest, authorization: str = Header(default="")) -> Response:
    if KEY and not hmac.compare_digest(authorization, f"Bearer {KEY}"):
        raise HTTPException(401, "bad key")
    if req.response_format != "mp3":
        raise HTTPException(400, "only mp3 is served")
    ref, ref_text = _voice(req.voice)
    with tempfile.TemporaryDirectory() as tmp, _lock:
        wav = os.path.join(tmp, "out.wav")
        _tts().infer(ref_file=ref, ref_text=ref_text, gen_text=req.input, file_wave=wav, seed=SEED, speed=req.speed)
        mp3 = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", wav, "-codec:a", "libmp3lame", "-q:a", "4", "-f", "mp3", "-"],
            capture_output=True, check=True,
        ).stdout
    return Response(mp3, media_type="audio/mpeg")
