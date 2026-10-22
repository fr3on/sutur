import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sutur_pipeline.errors import SpecError
from sutur_pipeline.tasks import DEFAULT, Status
from sutur_pipeline.tasks.chunk import clause_sequence, cut_panels, panel_words
from sutur_pipeline.tasks.plan import clean_prompt, parse_cast, repair_roles, style_files
from sutur_pipeline.tasks.spec import HINT, build_pages, final_prompt, page_sizes
from sutur_pipeline.volume import resolve
from tests.fakes import FakeLlm, context, make_book_volume

LONG = "كلمة " * 12   # 12 words


class ChunkTests(unittest.TestCase):
    def seq(self, *sentences: str) -> list[tuple[str, str]]:
        return [(f"1.{k}", s) for k, s in enumerate(sentences)]

    def test_a_panel_closes_at_a_sentence_end_after_26_words(self) -> None:
        panels = cut_panels(self.seq(LONG, LONG, LONG + ".", LONG, LONG + "."))
        self.assertEqual([[c for c, _ in p] for p in panels], [["1.0", "1.1", "1.2"], ["1.3", "1.4"]])

    def test_the_tail_joins_the_last_panel(self) -> None:
        seq = [("1.0", LONG * 3 + "."), ("2.0", "قصير")]
        self.assertEqual([[c for c, _ in p] for p in cut_panels(seq)], [["1.0", "2.0"]])

    def test_more_words_per_panel_means_fewer_panels(self) -> None:
        seq = [(f"{p}.{k}", LONG + ".") for p in range(1, 9) for k in range(3)]
        self.assertGreater(len(cut_panels(seq, 28)), len(cut_panels(seq, 56)))

    def test_task_writes_starts_and_chunks_that_agree(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_book_volume(Path(d))
            r = DEFAULT.get("chunk").run(context(ws, DEFAULT))
            self.assertEqual(r.status, Status.OK)
            starts = json.loads((ws.dir / "starts.json").read_text())
            lines = [x for x in (ws.dir / "chunks.txt").read_text(encoding="utf-8").splitlines() if x.startswith("[")]
            self.assertEqual(len(starts), len(lines))
            self.assertTrue(lines[0].startswith(f"[0] {starts[0]} "))
            self.assertNotIn("َ", lines[0])   # chunks are written without diacritics

    def test_panel_words_scale_with_length_between_28_and_60(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_book_volume(Path(d))
            src = resolve(ws, Path(d))
            self.assertEqual(panel_words(src, src.text()), 28)
            self.assertEqual(len(clause_sequence(src, src.text())), sum(len(c) for c in src.text().plain_clauses))


class SpecTests(unittest.TestCase):
    TAGS = {"prefix": "P.", "suffix": "S.", "swap_from": 10**9, "swap": {}, "giants": ["BIG"], "tags": {"ELD": "Elder (old man)", "BIG": "Giant (huge)"},
            "auto": [{"words": ["gun"], "text": "hands drawn right"}]}

    def test_page_sizes(self) -> None:
        self.assertEqual(page_sizes(12), [6, 6])
        self.assertEqual(page_sizes(105), [6] * 15 + [5] * 3)          # 18 pages, the finished Harafish volume
        self.assertEqual(page_sizes(219), [6] * 34 + [5] * 3)
        for n in range(1, 260):
            sizes = page_sizes(n)
            self.assertEqual(sum(sizes), n, n)
            self.assertTrue(all(1 <= x <= 6 for x in sizes), (n, sizes))
        self.assertEqual(page_sizes(13), [5, 4, 4])                       # short volumes: evenly filled pages
        with self.assertRaises(SpecError):
            page_sizes(0)

    def test_prompt_cleaning_and_tags(self) -> None:
        p, tall = final_prompt('{ELD} says "hello" to {ZZZ} holding a gun', 0, self.TAGS)
        self.assertFalse(tall)
        self.assertIn("Elder (old man)", p)
        self.assertNotIn("hello", p)
        self.assertNotIn("says", p)
        self.assertIn("a figure", p)           # an invented tag becomes a plain figure
        self.assertTrue(p.endswith("hands drawn right"))   # the gun adds its anatomy hint
        p2, tall2 = final_prompt("{BIG} stands", 0, self.TAGS)
        self.assertTrue(tall2 and p2.startswith(HINT))

    def test_pages_cover_the_text_without_gaps(self) -> None:
        n = 12
        order = [f"{p}.{k}" for p in range(1, 41) for k in range(3)]
        starts = [order[i * 10] for i in range(n)]
        pages = build_pages(["a scene"] * n, starts, self.TAGS, order, order[-1], "book9.json", 0)
        self.assertEqual(list(pages), ["p01", "p02"])
        panels = [p for page in pages.values() for r in page["rows"] for p in r["panels"]]
        self.assertEqual(len(panels), n)
        self.assertEqual(panels[0]["text"][0], order[0])
        for a, b in zip(panels, panels[1:], strict=False):   # each panel ends right before the next one starts
            self.assertEqual(order.index(a["text"][1]) + 1, order.index(b["text"][0]))
        self.assertEqual(panels[-1]["text"][1], order[-1])
        self.assertEqual({p["id"] for p in pages["p01"]["rows"][0]["panels"] + pages["p01"]["rows"][1]["panels"]} <= set("abcdef"), True)

    def test_blank_prompt_lines_are_refused(self) -> None:
        with self.assertRaises(SpecError):
            build_pages(["x", ""], ["1.0", "1.1"], self.TAGS, ["1.0", "1.1"], "1.1", "b", 0)

    def test_task_writes_specs_the_draw_task_can_use(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_book_volume(Path(d))
            DEFAULT.get("chunk").run(context(ws, DEFAULT))
            n = len(json.loads((ws.dir / "starts.json").read_text()))
            (ws.dir / "prompts.txt").write_text("\n".join(["A calm street"] * n) + "\n")
            ws.write_json("tags.json", {**self.TAGS, "tags": {"ELD": "Elder"}})
            r = DEFAULT.get("spec").run(context(ws, DEFAULT))
            self.assertEqual(r.status, Status.OK)
            spec = ws.page_specs()[0]
            self.assertEqual(spec.data["book"], "book9.json")
            self.assertEqual(spec.panel("a")["text"][0], json.loads((ws.dir / "starts.json").read_text())[0])


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:   # never reach the real site for a cover
        patcher = mock.patch("sutur_pipeline.tasks.plan.PlanTask._download", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_english_roles_are_translated_or_emptied(self) -> None:
        cast = parse_cast(json.dumps({"era": "e", "characters": [
            {"id": "a", "tag": "AAA", "ar_name": "أوليا", "ar_role": "Child with special eyes", "en_name": "Olya", "en_role": "Child with special eyes", "look": "l"},
            {"id": "b", "tag": "BBB", "ar_name": "الجدة", "ar_role": "Grandmother", "en_name": "Gran", "en_role": "Grandmother", "look": "l"}]}))
        self.assertEqual(len(cast["characters"]), 2)   # an English role no longer drops the character

        class Llm:
            def chat(self, *a: object, **k: object) -> str:
                return 'Sure: {"0": "طفلة ذات عينين خاصتين", "1": "Grandma"}'

        repair_roles(Llm(), cast["characters"])
        self.assertEqual([c["ar_role"] for c in cast["characters"]], ["طفلة ذات عينين خاصتين", ""])   # a bad translation is emptied

    def test_parse_cast_drops_names_that_are_not_plain_arabic(self) -> None:
        cast = parse_cast("sure: " + json.dumps(FakeLlm.CAST))
        self.assertEqual([c["id"] for c in cast["characters"]], ["elder"])   # "Ghost الشبح" has Latin letters
        with self.assertRaises(ValueError):
            parse_cast("no json at all")

    def test_style_files(self) -> None:
        files = style_files(parse_cast(json.dumps(FakeLlm.CAST)), "a desert town")
        self.assertIn("a desert town", files["tags"]["prefix"])
        self.assertEqual(files["tags"]["tags"], {"ELD": "The Elder (an old man in a white robe)"})
        self.assertEqual(files["keywords"]["ELD"], ["رجل", "عجوز", "شيخ", "حارة"])
        self.assertEqual(files["cast"]["cast"][0][:3], ["elder", "الرجل العجوز", "شيخ الحارة"])

    def test_clean_prompt(self) -> None:
        known = {"ELD"}
        out = clean_prompt('{ELD} and {XYZ} talking, a sign and "words", wearing glasses\nsecond line', known, lambda tag: True)
        self.assertIn("{ELD}", out)
        self.assertIn("a figure", out)        # unknown tag
        for banned in ("talking", "sign", "words", "glasses", "second line"):
            self.assertNotIn(banned, out)
        self.assertEqual(clean_prompt("{ELD} walks", known, lambda tag: False), "a figure walks")   # the passage does not name him
        self.assertTrue(clean_prompt("", known, lambda t: True).startswith("Wide establishing view"))

    def test_task_writes_everything_once_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_book_volume(Path(d))
            llm = FakeLlm()
            ctx = context(ws, DEFAULT)
            ctx.llm, ctx.options = llm, {"slug": "story-1"}
            DEFAULT.get("chunk").run(ctx)
            r = DEFAULT.get("plan").run(ctx)
            self.assertEqual(r.status, Status.OK, r.summary)
            for name in ("tags.json", "cast.json", "keywords.json", "publish.json", "cover.prompt.txt", "prompts.txt"):
                self.assertTrue((ws.dir / name).exists(), name)
            prompts = (ws.dir / "prompts.txt").read_text().splitlines()
            self.assertEqual(len(prompts), len(json.loads((ws.dir / "starts.json").read_text())))
            self.assertIn("{ELD}", prompts[0])
            self.assertEqual(ws.read_json("publish.json")["slug"], "story-1")
            (ws.dir / "prompts.txt").write_text("hand edited\n")
            calls = len(llm.calls)
            again = DEFAULT.get("plan").run(ctx)
            self.assertEqual(again.status, Status.SKIPPED)
            self.assertEqual((ws.dir / "prompts.txt").read_text(), "hand edited\n")
            self.assertEqual(len(llm.calls), calls)

    def test_the_first_plan_needs_a_slug_and_an_era_overrides_the_guess(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_book_volume(Path(d))
            ctx = context(ws, DEFAULT)
            ctx.llm = FakeLlm()
            DEFAULT.get("chunk").run(ctx)
            with self.assertRaisesRegex(SpecError, "--slug"):
                DEFAULT.get("plan").run(ctx)
            ctx.options = {"slug": "s", "era": "Cairo in 1900"}
            (ws.dir / "tags.json").unlink(missing_ok=True)
            DEFAULT.get("plan").run(ctx)
            self.assertIn("Cairo in 1900", ws.read_json("tags.json")["prefix"])


if __name__ == "__main__":
    unittest.main()
