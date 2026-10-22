import json
import tempfile
import unittest
from pathlib import Path

from sutur_pipeline.errors import SpecError
from sutur_pipeline.layout import GUTTER, MARGIN, PAGE_H, PAGE_W, draw_size, panel_boxes
from sutur_pipeline.models import PageSpec, PictureRef, write_atomic


class LayoutTests(unittest.TestCase):
    def test_panels_fill_the_page_right_to_left(self) -> None:
        rows = [{"h": 1, "panels": [{"id": "a"}, {"id": "b"}]}, {"h": 1, "panels": [{"id": "c"}]}]
        boxes = panel_boxes(rows)
        self.assertGreater(boxes["a"][0], boxes["b"][0])          # manga order: the first panel is on the right
        self.assertEqual(boxes["a"][2], PAGE_W - MARGIN)
        self.assertEqual(boxes["c"][0], MARGIN)
        self.assertEqual(boxes["c"][3] - 0, PAGE_H - MARGIN)
        self.assertEqual(boxes["a"][0] - boxes["b"][2], GUTTER)

    def test_relative_widths(self) -> None:
        boxes = panel_boxes([{"h": 1, "panels": [{"id": "a", "w": 2}, {"id": "b", "w": 1}]}])
        self.assertAlmostEqual((boxes["a"][2] - boxes["a"][0]) / (boxes["b"][2] - boxes["b"][0]), 2, delta=0.05)

    def test_draw_size_is_a_multiple_of_the_step(self) -> None:
        w, h = draw_size((0, 0, 400, 700))
        self.assertEqual((w % 32, h % 32), (0, 0))
        self.assertEqual(max(w, h), 1024)


class ModelTests(unittest.TestCase):
    def test_spec_roundtrip_keeps_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "p01.json"
            f.write_text(json.dumps({"rows": [{"h": 1, "panels": [{"id": "a", "prompt": "x", "extra": 1}]}], "custom": "keep"}), encoding="utf-8")
            spec = PageSpec.load(f)
            spec.panel("a")["seeds"] = [5]
            spec.save()
            data = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual((data["custom"], data["rows"][0]["panels"][0]["extra"], data["rows"][0]["panels"][0]["seeds"]), ("keep", 1, [5]))

    def test_bad_spec_is_a_spec_error(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "p01.json"
            f.write_text("{}", encoding="utf-8")
            with self.assertRaises(SpecError):
                PageSpec.load(f)
            f.write_text("not json", encoding="utf-8")
            with self.assertRaises(SpecError):
                PageSpec.load(f)

    def test_full_prompt_and_default_seeds(self) -> None:
        spec = PageSpec(Path("p01.json"), {"prefix": "P", "suffix": "S", "rows": [{"h": 1, "panels": [{"id": "a", "prompt": "mid"}]}]})
        panel = spec.panel("a")
        self.assertEqual(spec.full_prompt(panel), "P mid S")
        self.assertEqual(spec.seeds_for(panel), [1, 2, 3])

    def test_picture_names(self) -> None:
        ref = PictureRef.parse(Path("a-s12.png"))
        self.assertEqual((ref.panel, ref.seed), ("a", 12))  # type: ignore[union-attr]
        self.assertIsNone(PictureRef.parse(Path("notes.txt")))

    def test_atomic_write_leaves_no_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            write_atomic(Path(d) / "x" / "y.bin", b"abc")
            self.assertEqual([p.name for p in (Path(d) / "x").iterdir()], ["y.bin"])


if __name__ == "__main__":
    unittest.main()
