"""Plan task: the LLM writes what a person used to write for a volume. Files that already exist are never overwritten, so hand edits survive a rerun.

* `tags.json`, `keywords.json`, `cast.json`, `publish.json`, `cover.prompt.txt`: the cast with looks, the era, the cover scene (needs `--slug` the first time).
* `prompts.txt`: one English drawing prompt per panel, from `chunks.txt` (the chunk task).
* `cover-final.png` is fetched from the site when the volume already has a cover there ("coming soon" books)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .. import prompts
from ..errors import PipelineError, SpecError
from ..models import write_atomic
from ..volume import resolve
from .base import Context, Kind, Result, Task
from .registry import register

_ARABIC_NAME = re.compile(r"[؀-ۿ\s()،\-]+")
_LATIN = re.compile(r"[A-Za-z]")


def parse_cast(answer: str) -> dict[str, Any]:
    """The JSON object in the model's answer. A character whose Arabic name is not plain Arabic is dropped (the lettering font has no other glyphs);
    a role written in English is kept for `repair_roles` (the 7B model often answers the role in English)."""
    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        raise ValueError("no JSON in the answer")
    data: dict[str, Any] = json.loads(match.group(0))
    data["characters"] = [c for c in data["characters"] if not _LATIN.search(c["ar_name"]) and _ARABIC_NAME.fullmatch(c["ar_name"])]
    for c in data["characters"]:
        c["ar_role"] = str(c.get("ar_role", ""))
    return data


def repair_roles(llm: Any, characters: list[dict[str, Any]]) -> None:
    """Roles that came back with Latin letters are translated to Arabic in one more call.

    If that fails the role is left empty (the cast page then shows the name only)."""
    bad = [c for c in characters if _LATIN.search(c["ar_role"])]
    if not bad:
        return
    wanted = "\n".join(f"{i}: {c['en_role'] or c['ar_role']}" for i, c in enumerate(bad))
    try:
        ask = f'Translate each role to Arabic, at most 5 words, Arabic letters only. Return {{"0": "...", "1": "..."}} with the same numbers.\n{wanted}'
        answer = llm.chat("You translate short character roles into Arabic. Answer with a JSON object only.", ask, 400, 0.2)
        match = re.search(r"\{.*\}", answer, re.S)
        translated = json.loads(match.group(0)) if match else {}
    except (PipelineError, ValueError):
        translated = {}
    for i, c in enumerate(bad):
        role = str(translated.get(str(i), ""))
        c["ar_role"] = role if role and not _LATIN.search(role) else ""


def stem(word: str) -> str:
    return re.sub(r"^(ال|و)", "", word)


def style_files(cast: dict[str, Any], era: str) -> dict[str, Any]:
    """tags.json, keywords.json and cast.json contents for a parsed cast."""
    chars = cast["characters"]
    tags = {
        "prefix": prompts.STYLE_PREFIX.format(era=era), "suffix": prompts.STYLE_SUFFIX.format(era=era),
        "first_paragraph": 1, "swap_from": 10**9, "swap": {}, "giants": [], "auto": prompts.AUTO_WORDS,
        "tags": {c["tag"]: f"{c['en_name']} ({c['look']})" for c in chars},
    }
    keywords = {c["tag"]: [stem(w) for w in (c["ar_name"] + " " + c["ar_role"]).split() if len(stem(w)) > 2] for c in chars}
    cast_file = {"prefix": prompts.PORTRAIT_PREFIX.format(era=era),
                 "cast": [[c["id"], c["ar_name"], c["ar_role"], f"{c['en_name']}, {c['look']}. Single figure alone in the picture."] for c in chars]}
    return {"tags": tags, "keywords": keywords, "cast": cast_file}


_BUBBLE_WORDS = r"\b(speech bubbles?|thought bubbles?|balloons?|signs?|signboards?|banners?|posters?|captions?|labels?|inscriptions?|smartphones?|phones?)\b"
_TALK_WORDS = (r"\b(talking|talks|conversing|conversation|discussing|chatting|responds?|replies|replying|exclaims?|whispers?|shouts?|yells?|cries out|calls out"
               r"|asks?|answers?)\b")


def clean_prompt(raw: str, known: set[str], present: Callable[[str], bool]) -> str:
    """The first line of the model's answer made safe to draw: unknown or absent character tags become a plain figure, and every word that makes the
    image model draw speech bubbles, signs, phones or glasses is removed or softened."""
    t = re.sub(r"\s+", " ", raw.splitlines()[0] if raw else "").strip().strip('"')
    t = re.sub(r"\{(\w+)\}", lambda m: m.group(0) if m.group(1) in known and present(m.group(1)) else "a figure", t)
    t = re.sub(r"\b(saying|asking|said)\b", "speaking", t)
    t = re.sub(r"[\"“”][^\"“”]*[\"“”]", "", t)
    t = re.sub(r"\b(glasses|spectacles|eyeglasses)\b", "", t)
    t = re.sub(_TALK_WORDS, "facing", t)
    t = re.sub(r"\bcages\b", "baskets", re.sub(r"\bcage\b", "wicker basket", t, flags=re.I), flags=re.I)   # a fish in a birdcage for a porter's basket
    t = re.sub(_BUBBLE_WORDS, "", t)
    return t or "Wide establishing view of the place of the story, empty and atmospheric."


@register
class PlanTask(Task):
    name = "plan"
    kind = Kind.REVIEW   # model-written, a person reviews it
    requires = ("chunk",)
    description = "LLM writes the cast, tags, cover scene and one drawing prompt per panel (never overwrites existing files)."

    def preflight(self, ctx: Context) -> list[str]:
        return [] if ctx.workspace.read_text("chunks.txt") else ["chunks.txt is missing (run the chunk task)"]

    def run(self, ctx: Context) -> Result:
        ws, notes = ctx.workspace, []
        if ctx.dry_run:
            todo = [n for n in ("tags.json", "prompts.txt") if not (ws.dir / n).exists()]
            return Result.success(f"would write: {', '.join(todo) or 'nothing'}", planned=len(todo))
        llm = ctx.need_llm()
        if not (ws.dir / "tags.json").exists():
            self._cast(ctx, llm)
            notes.append("cast")
        if not (ws.dir / "prompts.txt").exists():
            notes.append(f"{self._prompts(ctx, llm)} prompts")
        if not (ws.dir / "cover-final.png").exists() and self._fetch_site_cover(ctx):
            notes.append("cover fetched from the site")
        if not notes:
            return Result.skipped("every plan file exists")
        return Result.success("wrote " + ", ".join(notes))

    # -- cast ---------------------------------------------------------------
    def _book_info(self, ctx: Context) -> tuple[str, str, dict[str, Any], str]:
        src = resolve(ctx.workspace, ctx.books_dir or ctx.workspace.root.parent)
        book = json.loads(src.book_path.read_text(encoding="utf-8"))
        text = book["chapters"][src.chapter]["text"]
        n = max(1, len(text) // 8)   # a volume can hold several tales: sample the whole text (8 slices), not only its opening
        sample = text[:3500] if len(text) <= 5600 else " … ".join(text[i * n : i * n + 700] for i in range(8))
        return book.get("title", ""), book.get("author", ""), book.get("metadata", {}), sample

    def _cast(self, ctx: Context, llm: Any) -> None:
        ws = ctx.workspace
        title, author, meta, sample = self._book_info(ctx)
        era_given = ctx.options.get("era")
        request = prompts.cast_request(title, author, str(meta.get("synopsis", "")), str(meta.get("main_characters", "")), sample, era_given)
        cast = None
        for temp in (0.2, 0.5, 0.7, 0.3):   # the model sometimes writes JSON with a missing comma: ask again with another temperature
            try:
                cast = parse_cast(llm.chat(prompts.CAST_SYSTEM, request, 1800, temp))
                break
            except (PipelineError, ValueError, KeyError, AttributeError):
                continue
        if cast is None:
            raise SpecError("the LLM did not return a valid cast")
        repair_roles(llm, cast["characters"])
        era = era_given or cast["era"]   # an explicit era beats the model's guess (it gets some books wrong, e.g. the Harafish)
        files = style_files(cast, era)
        ws.write_json("tags.json", files["tags"], indent=1)
        ws.write_json("keywords.json", files["keywords"], indent=1)
        ws.write_json("cast.json", files["cast"], indent=1)
        chars = cast["characters"]
        if not (ws.dir / "publish.json").exists():
            slug = ctx.options.get("slug")
            if not slug:
                raise SpecError("pass --slug <site slug> for the first plan of a volume")
            ws.write_json("publish.json", {"slug": slug, "seriesBook": "", "volumeNo": ws.ref.volume, "cast_picks": {},
                                           "characters": [{"id": c["id"], "nameEn": c["en_name"], "roleEn": c["en_role"]} for c in chars]}, indent=1)
        if not (ws.dir / "cover.prompt.txt").exists():
            try:
                looks = "; ".join(f"{c['en_name']} ({c['look']})" for c in chars[:3])
                scene = llm.chat(prompts.COVER_SYSTEM, prompts.cover_scene_request(looks, sample[:1500]), 120).splitlines()[0]
            except (PipelineError, IndexError):
                scene = "; ".join(c["en_name"] + ", " + c["look"] for c in chars[:2])
            ws.write_text("cover.prompt.txt", f"{prompts.COVER_PREFIX} {scene} {era}, period clothing only.")

    # -- prompts ------------------------------------------------------------
    def _prompts(self, ctx: Context, llm: Any) -> int:
        ws = ctx.workspace
        tags = ws.read_json("tags.json")["tags"]
        keywords = ws.read_json("keywords.json", {})
        chars = "\n".join(f"{{{k}}} = {v}" for k, v in tags.items())
        chunks = [re.sub(r"^\[\d+\] \S+ ", "", line.strip()) for line in (ws.read_text("chunks.txt") or "").splitlines() if line.startswith("[")]
        starts = ws.read_json("starts.json")
        if len(chunks) != len(starts):
            raise SpecError(f"chunks.txt has {len(chunks)} panels but starts.json {len(starts)}: run the chunk task again")
        system = prompts.PROMPT_SYSTEM + "\nMore rules from reviews:\n" + prompts.review_rules()
        known = set(tags)

        def one(i: int) -> str:
            def present(tag: str) -> bool:   # a character may be tagged only where the passage names it
                words = keywords.get(tag)
                return True if not words else any(w in chunks[i] for w in words)

            previous = chunks[i - 1][:300] if i else "(start of the story)"
            try:
                raw = llm.chat(system, prompts.panel_prompt_request(chars, previous, chunks[i][:900]), 120)
            except PipelineError:
                raw = ""
            return clean_prompt(raw, known, present)

        with ThreadPoolExecutor(ctx.settings.llm_threads) as ex:
            out = list(ex.map(one, range(len(chunks))))
        ws.write_text("prompts.txt", "\n".join(out) + "\n")
        return len(out)

    # -- cover from the site ------------------------------------------------
    @staticmethod
    def _download(url: str) -> bytes | None:
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            exc.close()
            return None
        except (urllib.error.URLError, TimeoutError):
            return None

    def _fetch_site_cover(self, ctx: Context) -> bool:
        publish = ctx.workspace.read_json("publish.json")
        if not publish:
            return False
        from io import BytesIO

        from PIL import Image

        for name in ("cover-v2.webp", "cover-v3.webp", "cover.webp"):
            data = self._download(f"{ctx.settings.site_url}/api/media/{publish['slug']}/{name}")
            if data:
                buf = BytesIO()
                Image.open(BytesIO(data)).convert("RGB").save(buf, "PNG")
                write_atomic(ctx.workspace.dir / "cover-final.png", buf.getvalue())
                return True
        return False
