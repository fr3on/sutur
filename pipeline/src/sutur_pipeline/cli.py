"""Command line: `sutur-pipeline run BOOK VOL draw scan pdf`, `status BOOK VOL`, `tasks`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from . import tasks as _tasks  # noqa: F401  (registers the built-in tasks)
from .clients import ImagePool, OpenAIChatClient, OpenAISpeechClient, OpenAIVisionClient
from .config import Settings
from .errors import PipelineError
from .models import VolumeRef
from .pipeline import Runner
from .render.fonts import FontSet
from .tasks.base import Context
from .tasks.registry import DEFAULT
from .workspace import Workspace


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sutur-pipeline", description=__doc__)
    p.add_argument("--root", type=Path, default=Path("comic"), help="folder that holds book<N>/v<V> (default: ./comic)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run stages on one volume")
    run.add_argument("book")
    run.add_argument("volume", type=int)
    run.add_argument("stages", nargs="+", help=f"e.g. draw vision pdf; `make` = {' '.join(MAKE)}")
    run.add_argument("--with-deps", action="store_true", help="also run the stages the chosen ones require")
    run.add_argument("--voice", help="voice name for the narrate stage (default: TTS_VOICE)")
    run.add_argument("--speed", type=float, help="speaking speed for the narrate stage (default: TTS_SPEED)")
    run.add_argument("--slug", help="site slug (the plan task needs it the first time)")
    run.add_argument("--era", help="period and place, overrides the LLM's guess, e.g. 'Cairo in the 19th century'")
    run.add_argument("--panel-words", type=int, help="words per panel for the chunk task (default: chosen from the length)")
    run.add_argument("--pages", help="build only these pages, e.g. 01,02")
    run.add_argument("--prod", help="production host for publish, user@host (or set SUTUR_PROD_HOST)")
    run.add_argument("--yes", action="store_true", help="go-ahead for guarded stages (publish)")
    run.add_argument("--books", type=Path, help="folder with the bookN.json files (default: the folder above --root)")
    run.add_argument("--dry-run", action="store_true", help="say what would be done, change nothing")

    status = sub.add_parser("status", help="what exists for a volume")
    status.add_argument("book")
    status.add_argument("volume", type=int)

    sub.add_parser("tasks", help="list the stages")
    return p


MAKE = ("spec", "draw", "textscan", "vision", "build", "cast", "cover", "lab", "pdf")   # everything between planning and publishing


def _options(args: argparse.Namespace) -> dict[str, str]:
    given = {"slug": args.slug, "era": args.era, "panel_words": args.panel_words, "pages": args.pages, "prod": args.prod}
    options = {k: str(v) for k, v in given.items() if v}
    if args.yes:
        options["yes"] = "1"
    return options


def _stages(names: Sequence[str]) -> list[str]:
    return [s for name in names for s in (MAKE if name == "make" else (name,))]


def _context(args: argparse.Namespace, settings: Settings) -> Context:
    ws = Workspace(args.root, VolumeRef(args.book, args.volume))
    # building a client opens no connection, so every task can be handed both
    return Context(
        workspace=ws, settings=settings, dry_run=getattr(args, "dry_run", False),
        images=ImagePool.from_settings(settings), vision=OpenAIVisionClient.from_settings(settings), tts=OpenAISpeechClient.from_settings(settings),
        books_dir=getattr(args, "books", None), llm=OpenAIChatClient.from_settings(settings),
        fonts=FontSet.from_env(os.environ, Path(os.environ.get("SITE_DIR", args.root.resolve().parent / "site"))),
        options=_options(args) if args.cmd == "run" else {},
    )


def _status(ws: Workspace) -> str:
    specs = ws.page_specs()
    drawn = sum(len(ws.pictures(s)) for s in specs)
    names = (
        "starts.json", "prompts.txt", "tags.json", "cast.json", "cover.prompt.txt", "publish.json",
        "cast.png", "cover-final.png", "lab.png", f"vol{ws.ref.volume}.pdf",
    )
    have = ", ".join(f"{n}:{'yes' if (ws.dir / n).exists() else 'NO'}" for n in names)
    return f"{ws.ref}: page specs {len(specs)}, pictures {drawn}, built pages {len(ws.built_pages())}\n  {have}"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    try:
        if args.cmd == "tasks":
            for a in DEFAULT:
                print(f"{a.name:8} {a.kind.value:7} requires {', '.join(a.requires) or '-':8} {a.description}")
            return 0
        if args.cmd == "status":
            print(_status(Workspace(args.root, VolumeRef(args.book, args.volume))))
            return 0
        settings = Settings.from_env(os.environ)
        if args.cmd == "run" and (args.voice or args.speed):
            settings = replace(settings, tts_voice=args.voice or settings.tts_voice, tts_speed=args.speed or settings.tts_speed)
        ctx = _context(args, settings)
        stages = _stages(args.stages)
        if not ctx.workspace.exists() and "chunk" not in stages:   # chunk is the task that creates a volume's folder
            print(f"no such volume folder: {ctx.workspace.dir}", file=sys.stderr)
            return 2
        report = Runner(DEFAULT).run(ctx, stages, with_deps=args.with_deps)
        return 0 if report.ok else 1
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
