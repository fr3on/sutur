"""Stand-ins for the model servers, so the tasks are tested without a GPU."""

from __future__ import annotations

import io
import json
import threading
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from sutur_pipeline.clients import ImagePool
from sutur_pipeline.config import Settings
from sutur_pipeline.models import VolumeRef
from sutur_pipeline.tasks.base import Context
from sutur_pipeline.tasks.registry import Registry
from sutur_pipeline.workspace import Workspace


def png(size: tuple[int, int] = (64, 64), shade: int = 200) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (shade, shade, shade)).save(buf, "PNG")
    return buf.getvalue()


class FakeImages:
    """Records every request; `fail_seeds` makes those seeds raise like a dead server."""

    def __init__(self, fail_seeds: set[int] | None = None) -> None:
        self.calls: list[tuple[str, int, int, int]] = []
        self.fail_seeds = fail_seeds or set()
        self._lock = threading.Lock()

    def generate(self, prompt: str, width: int, height: int, seed: int, negative: str | None = None) -> bytes:
        from sutur_pipeline.errors import TransportError

        with self._lock:
            self.calls.append((prompt, width, height, seed))
        if seed in self.fail_seeds:
            raise TransportError("server down")
        return png((width // 16, height // 16))


class FakeVision:
    """Answers the n-th question with `answers(n)` (1-based), as the model would: JSON inside a sentence."""

    def __init__(self, answers: Callable[[int], dict[str, bool]]) -> None:
        self._answers, self.n = answers, 0
        self._lock = threading.Lock()

    def ask(self, image_jpeg: bytes, question: str, max_tokens: int = 80) -> str:
        with self._lock:
            self.n += 1
            n = self.n
        return "Here you go: " + json.dumps(self._answers(n))


def make_volume(root: Path, panels: dict[str, list[str]] | None = None) -> Workspace:
    """book 9 volume 1 with one page spec p01: two rows, panels a, b (row 1) and c (row 2)."""
    ws = Workspace(root, VolumeRef("9", 1))
    ws.pages_dir.mkdir(parents=True)
    spec = {
        "book": "book9.json", "prefix": "Ink panel.", "suffix": "No text.",
        "rows": [
            {"h": 0.5, "panels": [{"id": "a", "prompt": "A road at dawn"}, {"id": "b", "prompt": "A rider", "seeds": [1, 2]}]},
            {"h": 0.5, "panels": [{"id": "c", "prompt": "A camp"}]},
        ],
    }
    (ws.pages_dir / "p01.json").write_text(json.dumps(spec), encoding="utf-8")
    return ws


def context(ws: Workspace, registry: Registry, images: FakeImages | None = None, vision: FakeVision | None = None, **settings: int) -> Context:
    s = Settings(draw_threads_per_server=2, vision_threads=2, llm_threads=2, **settings)   # type: ignore[arg-type]
    return Context(workspace=ws, settings=s, images=ImagePool([images or FakeImages()]), vision=vision, registry=registry)


ARABIC_PARAS = [
    "الفصل الأول",
    "قالَ الرجلُ: «مرحبًا بكم في المدينةِ.» ثم سارَ بعيدًا؛ وتبعَهُ الآخرون في الطريقِ الطويلِ بين البيوتِ القديمةِ.",
    "وفي الصباحِ خرجَ الناسُ إلى السوقِ. اشتروا الخبزَ والتمرَ والماءَ، وتحدثوا عن الأخبارِ الجديدةِ التي وصلتْ من المدينةِ البعيدةِ.",
    "وعندما جاءَ المساءُ عادَ كلٌّ إلى بيتِهِ، وأغلقوا الأبوابَ، ونامَ الجميعُ في هدوءٍ عميقٍ لا يقطعُهُ إلا نباحُ الكلابِ.",
    "ثم طلعَ الفجرُ على الحارةِ فاستيقظَ الرجلُ العجوزُ، ونظرَ إلى السماءِ الصافيةِ وقالَ: «اليومَ يومٌ جميلٌ.»",
]


def make_book_volume(root: Path, paragraphs: list[str] | None = None) -> Workspace:
    """book 9 volume 1 over a small Arabic text: `<root>/book9.json` (one chapter), `<root>/comic/book9/volumes.json`, workspace at `<root>/comic/book9/v1`."""
    paras = paragraphs or ARABIC_PARAS
    (root / "book9.json").write_text(
        json.dumps({"title": "قصة", "author": "مؤلف", "metadata": {"synopsis": "s", "main_characters": "الرجل"}, "chapters": [{"chapter_title": "x", "text": "\n\n".join(paras)}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "comic" / "book9").mkdir(parents=True, exist_ok=True)
    (root / "comic" / "book9" / "volumes.json").write_text(
        json.dumps({"volumes": [{"volume": 1, "source": "chapters[0]", "paragraphs": [1, len(paras)], "title_en": "One"}]}), encoding="utf-8")
    ws = Workspace(root / "comic", VolumeRef("9", 1))
    ws.dir.mkdir(parents=True, exist_ok=True)
    return ws


class FakeLlm:
    """Canned answers: a cast for the cast request, a tagged sentence for each panel."""

    CAST = {
        "era": "a desert town long ago",
        "characters": [
            {"id": "elder", "tag": "ELD", "ar_name": "الرجل العجوز", "ar_role": "شيخ الحارة", "en_name": "The Elder", "en_role": "old man", "look": "an old man in a white robe"},
            {"id": "ghost", "tag": "GHO", "ar_name": "Ghost الشبح", "ar_role": "شبح", "en_name": "Ghost", "en_role": "ghost", "look": "a pale figure"},
        ],
    }

    def __init__(self, panel_answer: str = "A wide view of the town at dawn with {ELD} walking") -> None:
        self.calls: list[str] = []
        self.panel_answer = panel_answer
        self._lock = threading.Lock()

    def chat(self, system: str, user: str, max_tokens: int = 300, temperature: float = 0.4) -> str:
        with self._lock:
            self.calls.append(user[:30])
        if "Return JSON" in user:
            return "Here is the cast: " + json.dumps(self.CAST)
        if system.startswith("You write one English sentence"):
            return "A tall elder stands at a city gate at dawn."
        return self.panel_answer


class FakeTransport:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command) -> None:  # type: ignore[no-untyped-def]
        self.commands.append(list(command))
