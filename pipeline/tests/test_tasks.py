import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sutur_pipeline.pipeline import Runner
from sutur_pipeline.tasks import DEFAULT, Status
from sutur_pipeline.tasks.draw import plan_jobs
from sutur_pipeline.tasks.pdf import pdf_inputs
from sutur_pipeline.tasks.review import reseed
from sutur_pipeline.tasks.vision import COVER, REDRAW, must_redraw, parse_flags, simplify
from tests.fakes import FakeImages, FakeVision, context, make_volume, png

QUIET = lambda _msg: None  # noqa: E731


class DrawTests(unittest.TestCase):
    def test_draws_every_missing_picture_once(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            images = FakeImages()
            r = DEFAULT.get("draw").run(context(ws, DEFAULT, images))
            self.assertEqual((r.status, r.data["drawn"]), (Status.OK, 3 + 2 + 3))   # a:3 seeds, b:2, c:3
            self.assertEqual(len(images.calls), 8)
            again = DEFAULT.get("draw").run(context(ws, DEFAULT, images))
            self.assertEqual(again.status, Status.SKIPPED)
            self.assertEqual(len(images.calls), 8)   # nothing redrawn

    def test_prompt_has_the_style_and_the_size_matches_the_box(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            jobs = plan_jobs(ws.page_specs()[0])
            self.assertTrue(jobs[0].prompt.startswith("Ink panel. A road at dawn"))
            self.assertTrue(jobs[0].prompt.endswith("No text."))
            self.assertEqual((jobs[0].width % 32, jobs[0].height % 32), (0, 0))

    def test_a_failing_seed_fails_the_stage_but_keeps_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            r = DEFAULT.get("draw").run(context(ws, DEFAULT, FakeImages(fail_seeds={2})))
            self.assertEqual(r.status, Status.FAILED)
            self.assertEqual(len(ws.pictures(ws.page_specs()[0])), 8 - 3)   # seed 2 of a, b and c
            retry = DEFAULT.get("draw").run(context(ws, DEFAULT, FakeImages()))
            self.assertEqual(retry.data["drawn"], 3)   # only the missing ones

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            ctx = context(ws, DEFAULT)
            ctx.dry_run = True
            r = DEFAULT.get("draw").run(ctx)
            self.assertEqual(r.data["planned"], 8)
            self.assertEqual(ws.pictures(ws.page_specs()[0]), [])


class VisionRulesTests(unittest.TestCase):
    def test_parse_flags_reads_json_inside_prose(self) -> None:
        self.assertEqual(parse_flags('Sure! {"nudity": true, "text": false, "bad_hands": true}'), ["nudity", "bad_hands"])
        with self.assertRaises(ValueError):
            parse_flags("no json here")

    def test_only_true_counts(self) -> None:
        self.assertEqual(parse_flags('{"text": "true", "cage": 1}'), [])

    def test_nudity_alone_is_kept_once_covered(self) -> None:
        self.assertEqual(must_redraw(["nudity"], "a bath scene"), ["nudity"])
        self.assertEqual(must_redraw(["nudity"], "a bath scene " + COVER), [])
        self.assertEqual(must_redraw(["text", "nudity"], "x " + COVER), ["text"])
        self.assertTrue(set(REDRAW) >= {"explicit", "minor_nude", "text"})

    def test_simplify(self) -> None:
        p, plain = simplify("A bath. Steam.", ["explicit"], 1)
        self.assertEqual((plain, p.endswith(COVER)), (False, True))
        self.assertEqual(simplify("x " + COVER, ["explicit"], 1), ("x " + COVER, False))   # covered already: unchanged
        p2, plain2 = simplify("A bath scene. More words", ["text"], 2)
        self.assertTrue(plain2 and p2.endswith("A bath scene"))

    def test_reseed_never_reuses_a_seed(self) -> None:
        panel = {"seeds": [1, 2, 3]}
        reseed(panel, on_disk=[1, 2, 3, 11], rejected={2})
        self.assertEqual(panel["seeds"], [1, 3, 21])


class VisionTaskTests(unittest.TestCase):
    def setUp(self) -> None:   # the text scan that closes the vision task is tested on its own: here it finds nothing
        for target, value in (("sutur_pipeline.tasks.textscan.has_text", []), ("sutur_pipeline.tasks.textscan.shutil.which", "/usr/bin/tesseract")):
            patcher = mock.patch(target, return_value=value) if isinstance(value, list) else mock.patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_flagged_pictures_are_rejected_redrawn_and_the_second_round_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            images = FakeImages()
            DEFAULT.get("draw").run(context(ws, DEFAULT, images))
            first = len(ws.pictures(ws.page_specs()[0]))
            # round 1 (8 pictures): the 3rd one has drawn text; round 2: everything is clean
            vision = FakeVision(lambda n: {"text": True} if n == 3 else {})
            r = DEFAULT.get("vision").run(context(ws, DEFAULT, images, vision))
            self.assertEqual((r.status, r.data["redrawn"], r.data["unresolved"]), (Status.OK, 1, []))
            spec = ws.page_specs()[0]
            self.assertEqual(len(ws.pictures(spec)), first)               # the rejected one was redrawn under a new seed
            self.assertEqual(len(list(spec.pictures_dir.glob("bad/*.png"))), 1)
            self.assertTrue(any(s > 10 for p in spec.panels() for s in p.get("seeds", [])))   # the threads decide which picture is the 3rd asked
            self.assertEqual(ws.read_json("mature.json"), {"nudity_panels": 0})

    def test_nudity_is_counted_and_covered_on_the_redraw(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            images = FakeImages()
            DEFAULT.get("draw").run(context(ws, DEFAULT, images))
            vision = FakeVision(lambda n: {"nudity": True} if n == 1 else {})
            DEFAULT.get("vision").run(context(ws, DEFAULT, images, vision))
            self.assertTrue(any(COVER in p["prompt"] for p in ws.page_specs()[0].panels()))

    def test_hopeless_pictures_are_reported_not_looped_forever(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            images = FakeImages()
            DEFAULT.get("draw").run(context(ws, DEFAULT, images))
            vision = FakeVision(lambda n: {"text": True})   # everything is always flagged
            r = DEFAULT.get("vision").run(context(ws, DEFAULT, images, vision, scan_rounds=2))
            self.assertEqual(r.status, Status.OK)
            self.assertTrue(r.data["unresolved"])
            self.assertIn("review them by hand", r.summary)

    def test_a_vision_server_that_never_answers_fails_the_stage(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            images = FakeImages()
            DEFAULT.get("draw").run(context(ws, DEFAULT, images))

            class Broken:
                def ask(self, *a: object, **k: object) -> str:
                    return "I cannot do that"

            ctx = context(ws, DEFAULT, images)
            ctx.vision = Broken()   # type: ignore[assignment]
            self.assertEqual(DEFAULT.get("vision").run(ctx).status, Status.FAILED)


class PdfTests(unittest.TestCase):
    def build(self, d: str) -> tuple[Path, object]:
        ws = make_volume(Path(d))
        ws.dir.joinpath("cover-final.png").write_bytes(png((432, 720)))
        for n in (1, 2):
            ws.pages_dir.joinpath(f"p{n:02d}.png").write_bytes(png((864, 1440)))
        return ws.dir, ws

    def test_order_and_optional_pages(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            vol, ws = self.build(d)
            names = [p.name for p in pdf_inputs(vol, ws.built_pages())]   # type: ignore[attr-defined]
            self.assertEqual(names, ["cover-final.png", "p01.png", "p02.png"])
            (vol / "lab.png").write_bytes(png())
            (vol / "cast.png").write_bytes(png())
            names = [p.name for p in pdf_inputs(vol, ws.built_pages())]   # type: ignore[attr-defined]
            self.assertEqual(names[:3], ["cover-final.png", "lab.png", "cast.png"])

    def test_writes_the_pdf_through_the_runner_and_records_stats(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            vol, ws = self.build(d)
            report = Runner(DEFAULT, QUIET).run(context(ws, DEFAULT), ["pdf"])   # type: ignore[arg-type]
            self.assertTrue(report.ok, report.failed)
            out = vol / "vol1.pdf"
            self.assertTrue(out.read_bytes().startswith(b"%PDF"))
            stats = json.loads((vol / "stats.json").read_text())
            self.assertIn("pdf", stats["stageSeconds"])
            self.assertIn("builtAt", stats)

    def test_preflight_names_what_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            problems = DEFAULT.get("pdf").preflight(context(ws, DEFAULT))
            self.assertEqual(len(problems), 2)
            report = Runner(DEFAULT, QUIET).run(context(ws, DEFAULT), ["pdf"])
            self.assertFalse(report.ok)
            self.assertIn("cover-final.png", report.failed.result.summary)   # type: ignore[union-attr]


class RunnerTests(unittest.TestCase):
    def test_full_chain_stops_at_the_first_failure(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            ctx = context(ws, DEFAULT, FakeImages(fail_seeds={1}), FakeVision(lambda n: {}))
            report = Runner(DEFAULT, QUIET).run(ctx, ["pdf", "vision", "draw"])
            self.assertEqual([o.stage for o in report.outcomes], ["draw"])   # draw failed, nothing after it ran
            self.assertFalse(report.ok)


if __name__ == "__main__":
    unittest.main()
