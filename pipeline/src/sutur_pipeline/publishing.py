"""Publishing a volume to the site: what is sent, and how it gets there.

Kept apart from the task so the package (pure file work) and the transport (ssh) are tested separately."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from .errors import PipelineError, SpecError
from .models import write_atomic
from .workspace import Workspace

PORTRAIT_PX = 512


@dataclass(frozen=True)
class Package:
    """The folder that is copied to the production host: publish.json, cover.png, book.pdf and the cast pictures."""

    folder: Path
    slug: str
    metadata: dict[str, Any]


def cast_version(now: float | None = None) -> int:
    """A new file name per publish (the CDN keeps old cast pictures for a day otherwise): minutes since the epoch, wrapped to 1..999."""
    return int((now if now is not None else time.time()) // 60) % 999 + 1


def build_package(ws: Workspace, now: float | None = None) -> Package:
    """Everything the site needs, written to `<volume>/publish/`. Raises SpecError for a missing input (the pdf, the cover, a cast portrait)."""
    meta = ws.read_json("publish.json")
    if not meta:
        raise SpecError("publish.json is missing")
    cast = ws.read_json("cast.json")["cast"]
    picks = meta.get("cast_picks", {})
    slug = meta["slug"]
    stage = ws.dir / "publish"
    stage.mkdir(exist_ok=True)
    version = cast_version(now)
    for old in stage.glob("cast-*.webp"):
        old.unlink()
    english = {c["id"]: c for c in meta["characters"]}
    characters = []
    for i, (cid, name, role, *_) in enumerate(cast, start=1):
        portrait = ws.dir / "cast" / f"{cid}-s{picks.get(cid, 1)}.png"
        if not portrait.exists():
            raise SpecError(f"cast portrait missing: {portrait}")
        im = Image.open(portrait).convert("L").convert("RGB")
        k = min(im.size)
        left = (im.width - k) // 2
        im.crop((left, 0, left + k, k)).resize((PORTRAIT_PX, PORTRAIT_PX), Image.Resampling.LANCZOS).save(stage / f"cast-{i}-v{version}.webp", quality=82)
        en = english[cid]
        characters.append({"name": name, "role": role, "nameEn": en["nameEn"], "roleEn": en["roleEn"], "img": f"/api/media/{slug}/cast-{i}-v{version}.webp"})
    meta["castList"] = characters
    meta["stats"] = run_stats(ws, now)
    mature = ws.read_json("mature.json")
    if mature and mature.get("nudity_panels", 0) > 0:
        meta["age"] = "18"   # a book with any (non-explicit) nudity is rated 18+
    write_atomic(stage / "publish.json", json.dumps(meta, ensure_ascii=False))
    cover = ws.dir / "cover-final.png"
    pdf = ws.dir / f"vol{ws.ref.volume}.pdf"
    for needed in (cover, pdf):
        if not needed.exists():
            raise SpecError(f"missing {needed}")
    Image.open(cover).convert("RGB").save(stage / "cover.png")
    write_atomic(stage / "book.pdf", pdf.read_bytes())
    return Package(stage, slug, meta)


def run_stats(ws: Workspace, now: float | None = None) -> dict[str, Any]:
    """The "making of" numbers shown on the book page, from stats.json and the files on disk."""
    stats = dict(ws.read_json("stats.json", {}) or {})
    specs = ws.page_specs()
    chunks = ws.read_text("chunks.txt")
    seconds = stats.get("stageSeconds", {})
    clock = now if now is not None else time.time()
    stats.update(
        pages=len(specs), panels=sum(1 for s in specs for _ in s.panels()), words=len(chunks.split()) if chunks else 0,
        llmTokens=stats.get("llmPromptTokens", 0) + stats.get("llmGenTokens", 0), llmCalls=stats.get("llmRequests", 0),
        images=sum(len(ws.pictures(s)) for s in specs), buildSeconds=sum(seconds.values()),
        reviewSeconds=max(0, int(clock) - stats["builtAt"]) if stats.get("builtAt") else 0,
    )
    return stats


class Transport(Protocol):
    def run(self, command: Sequence[str]) -> None: ...


class SshTransport:
    """ssh/scp to the production host with the operator's own agent (`ssh -A`): no key is stored anywhere on the GPU server."""

    def __init__(self, host: str) -> None:
        self.host = host

    def run(self, command: Sequence[str]) -> None:
        try:
            subprocess.run(list(command), check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise PipelineError(f"{command[0]} failed: {exc}") from exc


def upload(package: Package, transport: Transport, host: str) -> list[list[str]]:
    """Copy the package to `/tmp/pub-<slug>` on the host, run the remote publisher there (throwaway admin, the site's own admin API) and clean up.

    Returns the commands, in order, so the caller can show or test them."""
    remote = f"/tmp/pub-{package.slug}"
    script = resources.files("sutur_pipeline").joinpath("resources/publish_remote.py")
    with resources.as_file(script) as local_script:
        commands = [
            ["ssh", host, f"rm -rf {remote}; mkdir -p {remote}"],
            ["scp", "-q", "-r", *map(str, sorted(package.folder.glob("*"))), f"{host}:{remote}/"],
            ["scp", "-q", str(local_script), f"{host}:{remote}/"],
            ["ssh", host, f"python3 {remote}/publish_remote.py {remote}; rm -rf {remote}"],
        ]
        for command in commands:
            transport.run(command)
    return commands
