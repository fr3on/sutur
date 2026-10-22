"""The task contract.

An task owns one kind of process. It declares what it needs (`requires`: other tasks that must have run), checks its inputs (`preflight`) and does
its work in `run`, returning a Result. Two kinds exist:

* TRANSFORM tasks transform files (draw pictures, assemble a pdf). They are deterministic given their inputs and the model servers.
* REVIEW tasks look at the output of a transform task with a model and put things right (the scan task flags pictures and has them redrawn). They may call
  other tasks through the context, so a review task never needs to know how the transform task does its job.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..clients import ChatClient, ImagePool, TtsClient, VisionClient
from ..config import Settings
from ..errors import ConfigError
from ..publishing import Transport
from ..render.fonts import FontSet
from ..workspace import Workspace

if TYPE_CHECKING:
    from .registry import Registry


class Kind(Enum):
    TRANSFORM = "transform"
    REVIEW = "review"


class Status(Enum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Result:
    status: Status
    summary: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is not Status.FAILED

    @classmethod
    def success(cls, summary: str, **data: Any) -> Result:
        return cls(Status.OK, summary, data)

    @classmethod
    def failure(cls, summary: str, **data: Any) -> Result:
        return cls(Status.FAILED, summary, data)

    @classmethod
    def skipped(cls, summary: str) -> Result:
        return cls(Status.SKIPPED, summary)


@dataclass
class Context:
    """What an task gets: the volume's workspace, settings, model clients, and a way to call a sibling task."""

    workspace: Workspace
    settings: Settings
    images: ImagePool | None = None
    vision: VisionClient | None = None
    tts: TtsClient | None = None
    llm: ChatClient | None = None
    fonts: FontSet | None = None
    transport: Transport | None = None   # how publish reaches the host (ssh by default; tests pass a fake)
    options: dict[str, str] = field(default_factory=dict)   # per-run choices: era, slug, picks (cli flags), never secrets
    books_dir: Path | None = None   # where the bookN.json files are (default: the folder above the workspace root)
    registry: Registry | None = None
    dry_run: bool = False
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("sutur_pipeline"))

    def task(self, name: str) -> Task:
        if self.registry is None:
            raise ConfigError("this context has no registry")
        return self.registry.get(name)

    def need_images(self) -> ImagePool:
        if self.images is None:
            raise ConfigError("this stage needs an image server (set GPU_URL or GPU_URLS)")
        return self.images

    def need_fonts(self, *names: str) -> FontSet:
        if self.fonts is None:
            raise ConfigError("this stage needs fonts (FONT_DIR / LETTER_FONT)")
        self.fonts.need(*names)
        return self.fonts

    def need_llm(self) -> ChatClient:
        if self.llm is None:
            raise ConfigError("this stage needs the text LLM (set LLM_URL)")
        return self.llm

    def need_tts(self) -> TtsClient:
        if self.tts is None:
            raise ConfigError("this stage needs a speech server (set TTS_URL)")
        return self.tts

    def need_vision(self) -> VisionClient:
        if self.vision is None:
            raise ConfigError("this stage needs a vision server (set VL_URL)")
        return self.vision


class Task(ABC):
    """Subclass, set `name`, `kind` and `requires`, implement `run`, and decorate with `@register`."""

    name: ClassVar[str]
    kind: ClassVar[Kind] = Kind.TRANSFORM
    requires: ClassVar[tuple[str, ...]] = ()
    description: ClassVar[str] = ""
    guarded: ClassVar[bool] = False   # needs an explicit go-ahead (--yes) and is never run as a prerequisite

    def preflight(self, ctx: Context) -> list[str]:
        """Problems that make a run pointless (a missing input). Empty means go."""
        return []

    @abstractmethod
    def run(self, ctx: Context) -> Result: ...
