"""Typed views of the files the pipeline already writes. The JSON on disk stays the source of truth and keeps its unknown keys."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SpecError
from .layout import Box, panel_boxes

DEFAULT_SEEDS = (1, 2, 3)
_SEED_FILE = re.compile(r"^(?P<panel>.+)-s(?P<seed>\d+)\.png$")


def write_atomic(path: Path, data: bytes | str) -> None:
    """Write next to the target and rename, so a crash never leaves half a picture or half a spec behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp{os.getpid()}")
    if isinstance(data, str):
        tmp.write_text(data, encoding="utf-8")
    else:
        tmp.write_bytes(data)
    tmp.replace(path)


@dataclass(frozen=True)
class VolumeRef:
    """One volume of one book, e.g. book 60, volume 7."""

    book: str
    volume: int

    def __str__(self) -> str:
        return f"book{self.book} v{self.volume}"


@dataclass(frozen=True)
class PictureRef:
    """One drawn candidate for a panel: `<panel>-s<seed>.png` inside the page's folder."""

    path: Path
    panel: str
    seed: int

    @classmethod
    def parse(cls, path: Path) -> PictureRef | None:
        m = _SEED_FILE.match(path.name)
        return cls(path, m["panel"], int(m["seed"])) if m else None


class PageSpec:
    """A page spec (`pages/pNN.json`): rows of panels with prompts and seeds. Wraps the raw dict so unknown keys survive a save."""

    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        self.path, self.data = path, data
        if not isinstance(data.get("rows"), list) or not data["rows"]:
            raise SpecError(f"{path}: a page spec needs a non-empty 'rows' list")

    @classmethod
    def load(cls, path: Path) -> PageSpec:
        try:
            return cls(path, json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise SpecError(f"{path}: not valid JSON ({exc})") from exc

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def pictures_dir(self) -> Path:
        """`pages/p01/` next to `pages/p01.json`."""
        return self.path.with_suffix("")

    def panels(self) -> Iterator[dict[str, Any]]:
        for row in self.data["rows"]:
            yield from row["panels"]

    def panel(self, panel_id: str) -> dict[str, Any]:
        for p in self.panels():
            if p["id"] == panel_id:
                return p
        raise SpecError(f"{self.path}: no panel {panel_id!r}")

    def boxes(self) -> dict[str, Box]:
        return panel_boxes(self.data["rows"])

    def full_prompt(self, panel: dict[str, Any]) -> str:
        """Style prefix + the panel's own prompt + style suffix."""
        return " ".join(s for s in (self.data.get("prefix", ""), panel["prompt"], self.data.get("suffix", "")) if s).strip()

    def seeds_for(self, panel: dict[str, Any]) -> list[int]:
        return list(panel.get("seeds", DEFAULT_SEEDS))

    def save(self) -> None:
        write_atomic(self.path, json.dumps(self.data, ensure_ascii=False, indent=1))
