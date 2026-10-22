"""A whole tiny volume through every task, with fake model servers: chunk -> plan -> spec -> draw -> textscan -> vision -> build -> cast -> cover -> lab -> pdf -> publish."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import features

from sutur_pipeline.errors import PipelineError
from sutur_pipeline.pipeline import Runner, order
from sutur_pipeline.publishing import build_package, cast_version, upload
from sutur_pipeline.render.fonts import FontSet
from sutur_pipeline.tasks import DEFAULT, Status
from sutur_pipeline.tasks.textscan import simplify as text_simplify
from sutur_pipeline.tasks.textscan import words_from_tsv
from tests.fakes import FakeImages, FakeLlm, FakeTransport, FakeVision, context, make_book_volume

SITE = Path(__file__).resolve().parents[2] / "site"   # the lab page uses the site's fonts
FONTS = FontSet.from_env(os.environ, SITE)
HAVE_FONTS = features.check("raqm") and all(p.is_file() for p in (FONTS.caption, FONTS.title, FONTS.body, FONTS.latin, FONTS.vazir_bold, FONTS.vazir_regular))
QUIET = lambda _msg: None  # noqa: E731


class TextScanRules(unittest.TestCase):
    def row(self, word: str, conf: float) -> str:
        return "\t".join(["5", "1", "1", "1", "1", "1", "0", "0", "10", "10", str(conf), word])

    def test_only_confident_english_words_with_a_vowel_count(self) -> None:
        tsv = "\n".join([self.row("SALE", 90), self.row("xyz", 95), self.row("gone", 20), self.row("عربي", 99)])
        self.assertEqual(words_from_tsv(tsv, 60), ["SALE"])
        self.assertEqual(words_from_tsv(self.row("ok", 99), 60), [])        # too short to be a sign
        self.assertEqual(words_from_tsv(self.row("abc", 99), 60), [])       # fewer than four letters in all

    def test_prompts_are_only_simplified_from_the_third_round(self) -> None:
        self.assertEqual(text_simplify("A. B", ["x"], 2), ("A. B", False))
        self.assertEqual(text_simplify("A scene; more", ["x"], 3), ("A scene", True))


class GraphTests(unittest.TestCase):
    def test_make_order_follows_the_old_pipeline(self) -> None:
        stages = ["pdf", "lab", "cover", "cast", "build", "vision", "textscan", "draw", "spec", "plan", "chunk"]
        self.assertEqual(order(stages, DEFAULT), ["chunk", "plan", "spec", "draw", "textscan", "vision", "build", "cast", "cover", "lab", "pdf"])

    def test_with_deps_pulls_everything_before_pdf_but_never_publish(self) -> None:
        planned = order(["pdf"], DEFAULT, with_deps=True)
        self.assertEqual(planned[0], "chunk")
        self.assertEqual(planned[-1], "pdf")
        self.assertNotIn("publish", planned)


@unittest.skipUnless(HAVE_FONTS, "needs Pillow with Raqm and the Arabic system fonts")
class EndToEnd(unittest.TestCase):
    def test_every_stage_runs_and_the_package_is_complete(self) -> None:
        patches = [mock.patch("sutur_pipeline.tasks.plan.PlanTask._download", return_value=None),   # never reach the real site
                   mock.patch("sutur_pipeline.tasks.textscan.has_text", return_value=[]),
                   mock.patch("sutur_pipeline.tasks.textscan.shutil.which", return_value="/usr/bin/tesseract")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ws = make_book_volume(root)
            ctx = context(ws, DEFAULT, FakeImages(), FakeVision(lambda n: {}))
            ctx.llm, ctx.fonts, ctx.books_dir = FakeLlm(), FONTS, root
            ctx.options = {"slug": "story-1", "cast_seeds": "1"}
            runner = Runner(DEFAULT, QUIET)

            first = runner.run(ctx, ["chunk", "plan", "spec"])
            self.assertTrue(first.ok, first.failed)
            ws.write_json("publish.json", {**ws.read_json("publish.json"), "cover": {"series": "سلسلة", "volume": "المجلد الأول", "title": "قصة", "author": "مؤلف"}})

            second = runner.run(ctx, ["draw", "textscan", "vision", "build", "cast", "cover", "lab", "pdf"])
            self.assertTrue(second.ok, second.failed and second.failed.result.summary)
            self.assertEqual([o.stage for o in second.outcomes], ["draw", "textscan", "vision", "build", "cast", "cover", "lab", "pdf"])
            for name in ("cast.png", "cover-final.png", "lab.png", "vol1.pdf", "review/sheet-1.jpg", "mature.json", "stats.json"):
                self.assertTrue((ws.dir / name).exists(), name)
            self.assertTrue((ws.dir / "vol1.pdf").read_bytes().startswith(b"%PDF"))
            self.assertEqual(len(ws.built_pages()), len(ws.page_specs()))
            self.assertEqual(set(ws.read_json("stats.json")["stageSeconds"]), {"chunk", "plan", "spec", "draw", "textscan", "vision", "build", "cast", "cover", "lab", "pdf"})

            # rerunning changes nothing and says so
            again = runner.run(ctx, ["draw", "cover"])
            self.assertEqual([o.result.status for o in again.outcomes], [Status.SKIPPED, Status.SKIPPED])

            # publish: refuses without --yes, then sends exactly four commands through the transport
            ctx.transport = FakeTransport()
            ctx.options["prod"] = "deploy@example.invalid"
            blocked = runner.run(ctx, ["publish"])
            self.assertFalse(blocked.ok)
            self.assertIn("--yes", blocked.failed.result.summary)  # type: ignore[union-attr]
            self.assertEqual(ctx.transport.commands, [])
            ctx.options.update(yes="1", prod="deploy@example.invalid")
            done = runner.run(ctx, ["publish"])
            self.assertTrue(done.ok, done.failed and done.failed.result.summary)
            commands = ctx.transport.commands
            self.assertEqual([c[0] for c in commands], ["ssh", "scp", "scp", "ssh"])
            self.assertIn("publish_remote.py", commands[2][2])
            package = ws.dir / "publish"
            self.assertEqual(sorted(p.name for p in package.glob("*") if not p.name.startswith("cast-")), ["book.pdf", "cover.png", "publish.json"])
            meta = json.loads((package / "publish.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["slug"], "story-1")
            self.assertEqual(len(meta["castList"]), 1)   # the cast of the fake llm: one plain-Arabic name survives
            self.assertTrue(meta["castList"][0]["img"].startswith("/api/media/story-1/cast-1-v"))
            self.assertGreater(meta["stats"]["images"], 0)
            self.assertNotIn("age", meta)


class PublishingTests(unittest.TestCase):
    def test_cast_version_is_a_small_changing_number(self) -> None:
        self.assertEqual(cast_version(0), 1)
        self.assertNotEqual(cast_version(60 * 5), cast_version(60 * 6))
        self.assertTrue(all(1 <= cast_version(t * 60) <= 999 for t in range(0, 5000, 37)))

    def test_missing_inputs_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_book_volume(Path(d))
            with self.assertRaises(PipelineError):
                build_package(ws)    # no publish.json
            ws.write_json("publish.json", {"slug": "s", "characters": []})
            ws.write_json("cast.json", {"cast": []})
            with self.assertRaisesRegex(PipelineError, "missing"):
                build_package(ws)    # no cover / pdf

    def test_nudity_makes_the_book_18_plus(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_book_volume(Path(d))
            ws.write_json("publish.json", {"slug": "s", "characters": []})
            ws.write_json("cast.json", {"cast": []})
            ws.write_json("mature.json", {"nudity_panels": 2})
            from tests.fakes import png

            (ws.dir / "cover-final.png").write_bytes(png())
            (ws.dir / "vol1.pdf").write_bytes(b"%PDF-1.4")
            package = build_package(ws)
            self.assertEqual(package.metadata["age"], "18")
            transport = FakeTransport()
            upload(package, transport, "root@host")
            self.assertEqual(len(transport.commands), 4)
            self.assertIn("/tmp/pub-s", transport.commands[0][2])


if __name__ == "__main__":
    unittest.main()


class PublishHostTests(unittest.TestCase):
    def test_there_is_no_default_host(self) -> None:
        from sutur_pipeline.errors import ConfigError

        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUTUR_PROD_HOST", None)
            ws = make_book_volume(Path(d))
            ctx = context(ws, DEFAULT)
            ctx.options = {"yes": "1"}
            with self.assertRaisesRegex(ConfigError, "production host"):
                DEFAULT.get("publish").run(ctx)
