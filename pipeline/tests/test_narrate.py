import json
import tempfile
import unittest
from pathlib import Path

from sutur_pipeline.clients import JsonHttp, OpenAISpeechClient
from sutur_pipeline.errors import SpecError, TransportError
from sutur_pipeline.source import BookText
from sutur_pipeline.tasks import DEFAULT, Status
from sutur_pipeline.tasks.narrate import clip_key, plan_clips, spoken
from tests.fakes import context, make_volume

CHAPTER = "العنوان\n\nقالَ: «مرحبًا بكم.» ثم ضحك؛ وسارَ بعيدًا.\nوتبعَهُ الآخرون.\n\nفصل ثانٍ، قصير."


class FakeTts:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, float]] = []
        self.fail = fail

    def speak(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        self.calls.append((text, voice, speed))
        if self.fail:
            raise TransportError("tts down")
        return b"ID3" + text.encode()


def volume(root: Path):
    (root / "book9.json").write_text(json.dumps({"chapters": [{"chapter_title": "x", "text": CHAPTER}]}), encoding="utf-8")
    ws = make_volume(root / "comic")
    spec_file = ws.pages_dir / "p01.json"
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    spec["chapter"] = 0
    spec["rows"][0]["panels"][0]["text"] = ["2.0", "2.1"]   # paragraph 2: clauses 0 and 1
    spec["rows"][1]["panels"][0]["text"] = ["3.0", "3.0"]
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    return ws


class BookTextTests(unittest.TestCase):
    def test_clauses_are_numbered_like_the_old_tools(self) -> None:
        book = BookText(["أولى. ثانية؛ ثالثة", "رابعة."])
        self.assertEqual(book.clauses, [["أولى.", "ثانية؛", "ثالثة"], ["رابعة."]])
        self.assertEqual(book.between("1.1", "2.0"), "ثانية؛ ثالثة رابعة.")

    def test_hard_wrapped_lines_are_joined(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "b.json"
            f.write_text(json.dumps({"chapters": [{"text": CHAPTER}]}), encoding="utf-8")
            book = BookText.from_file(f, 0)
            self.assertEqual(len(book.paragraphs), 3)
            self.assertNotIn("\n", book.paragraphs[1])

    def test_bad_references(self) -> None:
        book = BookText(["أ. ب."])
        for a, b in (("9.0", "9.1"), ("1.1", "1.0"), ("x", "1.0")):
            with self.assertRaises(SpecError):
                book.between(a, b)


class PlanTests(unittest.TestCase):
    def test_clips_follow_the_panel_text_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = volume(Path(d))
            clips = plan_clips(ws.page_specs(), Path(d), "v", 1.0, "m")
            self.assertEqual([c.name for c in clips], ["p01/a", "p01/c"])   # panel b has no text
            self.assertIn("مرحبًا", clips[0].text)                          # diacritics kept
            self.assertEqual(clips[1].text, "فصل ثانٍ،")

    def test_key_changes_with_voice_speed_model_and_text(self) -> None:
        base = clip_key("t", "v", 1.0, "m")
        self.assertEqual(base, clip_key("t", "v", 1.0, "m"))
        self.assertEqual(len({base, clip_key("t", "w", 1.0, "m"), clip_key("t", "v", 1.2, "m"), clip_key("t", "v", 1.0, "n"), clip_key("u", "v", 1.0, "m")}), 5)

    def test_spoken_text(self) -> None:
        self.assertEqual(spoken("  كلـــمة \n  أخرى "), "كلمة أخرى")


class NarrateTaskTests(unittest.TestCase):
    def ctx(self, ws, tts):
        c = context(ws, DEFAULT)
        c.tts, c.books_dir = tts, ws.root.parent
        return c

    def test_speaks_once_then_only_what_changed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = volume(Path(d))
            tts = FakeTts()
            r = DEFAULT.get("narrate").run(self.ctx(ws, tts))
            self.assertEqual((r.status, r.data["made"]), (Status.OK, 2))
            manifest = json.loads((ws.dir / "audio" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["clips"]), {"p01/a", "p01/c"})
            self.assertTrue((ws.dir / "audio" / "p01" / "a.mp3").read_bytes().startswith(b"ID3"))
            self.assertEqual(DEFAULT.get("narrate").run(self.ctx(ws, tts)).status, Status.SKIPPED)
            self.assertEqual(len(tts.calls), 2)
            # a different voice redoes every clip
            c = self.ctx(ws, tts)
            c.settings = type(c.settings)(**{**c.settings.__dict__, "tts_voice": "other"})
            self.assertEqual(DEFAULT.get("narrate").run(c).data["made"], 2)

    def test_failures_are_reported_and_the_rest_kept(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = volume(Path(d))
            r = DEFAULT.get("narrate").run(self.ctx(ws, FakeTts(fail=True)))
            self.assertEqual(r.status, Status.FAILED)
            self.assertFalse((ws.dir / "audio" / "p01" / "a.mp3").exists())
            retry = DEFAULT.get("narrate").run(self.ctx(ws, FakeTts()))
            self.assertEqual(retry.data["made"], 2)

    def test_dry_run_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = volume(Path(d))
            c = self.ctx(ws, FakeTts())
            c.dry_run = True
            self.assertEqual(DEFAULT.get("narrate").run(c).data["planned"], 2)
            self.assertFalse((ws.dir / "audio").exists())

    def test_removed_panels_leave_the_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = volume(Path(d))
            DEFAULT.get("narrate").run(self.ctx(ws, FakeTts()))
            spec_file = ws.pages_dir / "p01.json"
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
            del spec["rows"][1]["panels"][0]["text"]
            spec_file.write_text(json.dumps(spec), encoding="utf-8")
            DEFAULT.get("narrate").run(self.ctx(ws, FakeTts()))   # nothing to speak, but the manifest must forget the removed caption
            manifest = json.loads((ws.dir / "audio" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["clips"]), {"p01/a"})


class SpeechClientTests(unittest.TestCase):
    def test_rejects_an_answer_that_is_not_an_mp3(self) -> None:
        class Http(JsonHttp):
            def post_bytes(self, path, body):  # type: ignore[no-untyped-def]
                return b'{"error": "no such voice"}'

        with self.assertRaisesRegex(TransportError, "not an mp3"):
            OpenAISpeechClient(Http("http://x"), "m").speak("t", "v")


if __name__ == "__main__":
    unittest.main()
