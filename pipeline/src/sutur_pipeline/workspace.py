"""Where a volume lives on disk. The layout is the one the existing tools use (comic/bookN/vV/...), so both can run on the same folder."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import SpecError
from .models import PageSpec, PictureRef, VolumeRef, write_atomic

_PAGE_SPEC = re.compile(r"^p\d\d\.json$")


class Workspace:
    """`<root>/book<BOOK>/v<VOL>/` with `pages/pNN.json`, `pages/pNN/<panel>-s<seed>.png`, `pages/pNN.png`, cover-final.png, ..."""

    def __init__(self, root: Path, ref: VolumeRef) -> None:
        self.root, self.ref = root, ref
        self.dir = root / f"book{ref.book}" / f"v{ref.volume}"

    @property
    def pages_dir(self) -> Path:
        return self.dir / "pages"

    def exists(self) -> bool:
        return self.dir.is_dir()

    def page_specs(self) -> list[PageSpec]:
        if not self.pages_dir.is_dir():
            return []
        return [PageSpec.load(p) for p in sorted(self.pages_dir.iterdir()) if _PAGE_SPEC.match(p.name)]

    def pictures(self, spec: PageSpec, panel_id: str | None = None) -> list[PictureRef]:
        """The candidate pictures drawn so far (not the ones moved to bad/), sorted by panel and seed."""
        if not spec.pictures_dir.is_dir():
            return []
        refs = (PictureRef.parse(p) for p in spec.pictures_dir.iterdir())
        return sorted((r for r in refs if r and (panel_id is None or r.panel == panel_id)), key=lambda r: (r.panel, r.seed))

    def built_pages(self) -> list[Path]:
        return sorted(p for p in self.pages_dir.glob("p[0-9][0-9].png")) if self.pages_dir.is_dir() else []

    def reject(self, picture: PictureRef) -> Path:
        """Move a picture into the page's bad/ folder (kept for review, never deleted)."""
        target = picture.path.parent / "bad" / picture.path.name
        target.parent.mkdir(exist_ok=True)
        picture.path.replace(target)
        return target

    # small json files the other stages share
    def read_json(self, name: str, default: Any = None) -> Any:
        data = self.read_json_at(self.dir / name)
        return default if data is None else data

    @staticmethod
    def read_json_at(path: Path) -> Any:
        """A json file anywhere (None when it does not exist)."""
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SpecError(f"{path}: not valid JSON ({exc})") from exc

    def write_json(self, name: str, data: Any, indent: int | None = None) -> None:
        write_atomic(self.dir / name, json.dumps(data, ensure_ascii=False, indent=indent))

    def write_text(self, name: str, text: str) -> None:
        write_atomic(self.dir / name, text)

    def read_text(self, name: str) -> str | None:
        f = self.dir / name
        return f.read_text(encoding="utf-8") if f.exists() else None
