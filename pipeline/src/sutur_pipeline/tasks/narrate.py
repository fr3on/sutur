"""Narrate task: one mp3 per lettered panel, the spoken version of the panel's caption.

The text is the panel's `"text": [first, last]` clause range from the book (diacritics kept, so the voice pronounces the words correctly).
Clips go to `audio/<page>/<panel>.mp3`, described by `audio/manifest.json`; a clip is redone only when its text, voice, speed or model changed.
"""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..errors import PipelineError
from ..models import PageSpec, write_atomic
from ..source import BookText, find_book_file
from .base import Context, Kind, Result, Task
from .registry import register

MANIFEST = "audio/manifest.json"
_SPACES = re.compile(r"\s+")


def spoken(text: str) -> str:
    """What is sent to the voice: one line, tatweel removed (it only stretches the letters on screen)."""
    return _SPACES.sub(" ", text.replace("ـ", "")).strip()


def clip_key(text: str, voice: str, speed: float, model: str) -> str:
    """Changes whenever the clip would sound different."""
    return hashlib.sha256(f"{model}\0{voice}\0{speed}\0{text}".encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Clip:
    page: str
    panel: str
    text: str
    key: str

    @property
    def name(self) -> str:
        return f"{self.page}/{self.panel}"

    @property
    def file(self) -> str:
        return f"{self.name}.mp3"


def plan_clips(specs: list[PageSpec], books_dir: Path, voice: str, speed: float, model: str) -> list[Clip]:
    """Every lettered panel of the volume as a clip to make, in reading order."""
    books: dict[tuple[Path, int], BookText] = {}
    clips: list[Clip] = []
    for spec in specs:
        wanted = [p for p in spec.panels() if p.get("text")]
        if not wanted:
            continue
        path = find_book_file(spec.data["book"], books_dir)
        chapter = int(spec.data.get("chapter", 2))
        book = books.setdefault((path, chapter), BookText.from_file(path, chapter))
        for panel in wanted:
            text = spoken(book.between(*panel["text"]))
            clips.append(Clip(spec.name, panel["id"], text, clip_key(text, voice, speed, model)))
    return clips


@register
class NarrateTask(Task):
    name = "narrate"
    kind = Kind.TRANSFORM
    description = "Speak every lettered panel's caption into audio/<page>/<panel>.mp3 with the speech server (TTS_URL, TTS_VOICE, TTS_SPEED)."

    def preflight(self, ctx: Context) -> list[str]:
        return [] if ctx.workspace.page_specs() else [f"no page specs in {ctx.workspace.pages_dir}"]

    @staticmethod
    def _save(ctx: Context, clips: dict[str, dict[str, object]]) -> None:
        s = ctx.settings
        manifest = {"voice": s.tts_voice, "model": s.tts_model, "speed": s.tts_speed, "clips": clips}
        write_atomic(ctx.workspace.dir / MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))

    def run(self, ctx: Context) -> Result:
        s = ctx.settings
        books_dir = ctx.books_dir or ctx.workspace.root.parent
        clips = plan_clips(ctx.workspace.page_specs(), books_dir, s.tts_voice, s.tts_speed, s.tts_model)
        if not clips:
            return Result.skipped("no panel has caption text")
        manifest = ctx.workspace.read_json(MANIFEST, {}) or {}
        done = manifest.get("clips", {})
        todo = [c for c in clips if done.get(c.name, {}).get("key") != c.key or not (ctx.workspace.dir / "audio" / c.file).exists()]
        live = {c.name for c in clips}
        if not todo:
            if set(done) != live and not ctx.dry_run:   # a caption was removed: the manifest forgets it, the old mp3 stays on disk for review
                self._save(ctx, {k: v for k, v in done.items() if k in live})
            return Result.skipped(f"all {len(clips)} clips are up to date")
        if ctx.dry_run:
            return Result.success(f"would speak {len(todo)} of {len(clips)} clips with voice {s.tts_voice!r}", planned=len(todo))
        tts = ctx.need_tts()

        def one(clip: Clip) -> tuple[Clip, int, str | None]:
            try:
                audio = tts.speak(clip.text, s.tts_voice, s.tts_speed)
            except PipelineError as exc:
                return clip, 0, f"{clip.name}: {exc}"
            write_atomic(ctx.workspace.dir / "audio" / clip.file, audio)
            ctx.log.info("spoke %s (%d chars)", clip.name, len(clip.text))
            return clip, len(audio), None

        with ThreadPoolExecutor(s.tts_threads) as ex:
            outcomes = list(ex.map(one, todo))
        errors = [e for _, _, e in outcomes if e]
        for clip, size, err in outcomes:
            if not err:
                done[clip.name] = {"file": clip.file, "key": clip.key, "chars": len(clip.text), "bytes": size}
        self._save(ctx, {k: v for k, v in done.items() if k in live})   # the manifest never lists a panel that was removed
        made = len(todo) - len(errors)
        if errors:
            return Result.failure(f"spoke {made} of {len(todo)} clips; {len(errors)} failed (first: {errors[0]})", made=made, errors=errors)
        return Result.success(f"spoke {made} clips ({len(clips) - len(todo)} were up to date)", made=made)
