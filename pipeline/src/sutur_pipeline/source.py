"""The book text a panel's caption comes from. Paragraphs and clauses are numbered exactly as the old `tools/page_text.py` numbers them,
so a panel's `"text": ["3.0", "3.4"]` means the same thing here (paragraph 3 clause 0 through paragraph 3 clause 4)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .errors import SpecError

_MARKS = re.compile("[ً-ٰٟـ]")   # tashkeel and tatweel
_CLAUSE_END = re.compile(r"(?<=[.؛،:»])\s+")


def strip_marks(text: str) -> str:
    return _MARKS.sub("", text)


class BookText:
    """One chapter of a book as paragraphs, each split into clauses. The diacritics are kept: they make a voice pronounce the words correctly."""

    def __init__(self, paragraphs: list[str]) -> None:
        self.paragraphs = paragraphs
        self.clauses = [[c.strip() for c in _CLAUSE_END.split(p) if c.strip()] for p in paragraphs]
        self.plain_clauses = [[strip_marks(c) for c in cs] for cs in self.clauses]   # what the page captions and the prompts use
        self._order = [(p + 1, k) for p, cs in enumerate(self.clauses) for k in range(len(cs))]
        self.order = tuple(self._order)

    @classmethod
    def from_file(cls, path: Path, chapter: int) -> BookText:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))["chapters"][chapter]["text"]
        except (OSError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise SpecError(f"{path}: cannot read chapter {chapter} ({exc})") from exc
        return cls([re.sub(r"\s*\n\s*", " ", p).strip() for p in raw.split("\n\n") if p.strip()])

    @staticmethod
    def _ref(ref: str) -> tuple[int, int]:
        try:
            p, k = ref.split(".")
            return int(p), int(k)
        except ValueError as exc:
            raise SpecError(f"bad clause reference {ref!r} (expected paragraph.index, like 3.0)") from exc

    def between(self, first: str, last: str, marks: bool = True) -> str:
        """The clauses from `first` to `last`, inclusive, joined with spaces (with or without diacritics)."""
        a, b = self._ref(first), self._ref(last)
        try:
            i, j = self._order.index(a), self._order.index(b)
        except ValueError as exc:
            raise SpecError(f"clause {first!r} or {last!r} is not in this chapter") from exc
        if j < i:
            raise SpecError(f"clause range {first!r}..{last!r} runs backwards")
        source = self.clauses if marks else self.plain_clauses
        return " ".join(source[p - 1][k] for p, k in self._order[i : j + 1])


def find_book_file(name: str, *folders: Path) -> Path:
    """`book3.json` as written in a page spec: tried as given, then in each folder."""
    for candidate in (Path(name), *(f / name for f in folders)):
        if candidate.is_file():
            return candidate
    raise SpecError(f"book file {name!r} not found (looked in {', '.join(str(f) for f in folders) or 'the current folder'})")
