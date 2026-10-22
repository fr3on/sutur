"""Which text a volume is made from: the book file, the chapter and the paragraph range. The rules of the old `tools/volctx.py`.

* Book 3 (the Harafish): one tale per chapter, volume N is chapter N-1 from paragraph 3 on.
* Any other book: `<root>/book<N>/volumes.json` lists the volumes; an entry has either `"paragraphs": [first, last]` of `"source": "chapters[i]"`,
  or `"chapters": [a, b]`, whole chapters merged into one text written to `<volume>/book.json`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import SpecError
from .models import write_atomic
from .source import BookText, find_book_file
from .workspace import Workspace

HARAFISH = "3"


@dataclass(frozen=True)
class VolumeSource:
    book_ref: str          # as written into page specs: "book3.json", or the path of the merged text
    book_path: Path
    chapter: int
    first: int             # first paragraph of the volume (1-based)
    last: int | None       # last paragraph, None = to the end

    def text(self) -> BookText:
        return BookText.from_file(self.book_path, self.chapter)

    def in_range(self, paragraph: int) -> bool:
        return self.first <= paragraph <= (self.last or 10**9)


def resolve(ws: Workspace, books_dir: Path, write_merged: bool = True) -> VolumeSource:
    ref, vol = ws.ref, ws.ref.volume
    name = f"book{ref.book}.json"
    if ref.book == HARAFISH:
        return VolumeSource(name, find_book_file(name, books_dir), vol - 1, 3, None)
    volumes = ws.read_json_at(ws.root / f"book{ref.book}" / "volumes.json")
    if volumes is None:
        raise SpecError(f"{ws.root / f'book{ref.book}' / 'volumes.json'} is missing: it lists the volumes of book {ref.book}")
    entry = next((v for v in volumes["volumes"] if v["volume"] == vol), None)
    if entry is None:
        raise SpecError(f"volumes.json of book {ref.book} has no volume {vol}")
    path = find_book_file(name, books_dir)
    if "chapters" in entry:
        a, b = entry["chapters"]
        merged = ws.dir / "book.json"
        if write_merged and not merged.exists():
            src = json.loads(path.read_text(encoding="utf-8"))
            text = "\n\n".join(c["text"].strip() for c in src["chapters"][a : b + 1])
            write_atomic(merged, json.dumps({"chapters": [{"chapter_title": entry.get("title_en", ""), "text": text}]}, ensure_ascii=False))
        return VolumeSource(str(merged), merged, 0, 1, None)
    first, last = entry["paragraphs"]
    m = re.search(r"chapters\[(\d+)\]", entry["source"])
    if not m:
        raise SpecError(f"volume {vol}: cannot read the chapter from source {entry['source']!r}")
    return VolumeSource(name, path, int(m.group(1)), first, last)
