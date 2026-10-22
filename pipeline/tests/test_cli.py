import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from sutur_pipeline.cli import main
from tests.fakes import make_volume


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_tasks_lists_every_registered_task(self) -> None:
        code, out, _ = run("tasks")
        self.assertEqual(code, 0)
        for name in ("draw", "scan", "narrate", "pdf"):
            self.assertIn(name, out)

    def test_status_counts_what_exists(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            make_volume(Path(d))
            code, out, _ = run("--root", d, "status", "9", "1")
            self.assertEqual(code, 0)
            self.assertIn("page specs 1, pictures 0, built pages 0", out)

    def test_dry_run_plans_without_a_server(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ws = make_volume(Path(d))
            code, out, _ = run("--root", d, "run", "9", "1", "draw", "--dry-run")
            self.assertEqual(code, 0)
            self.assertIn("would draw 8 pictures", out)
            self.assertFalse(list(ws.pages_dir.glob("p01/*.png")))

    def test_unknown_stage_and_missing_volume_are_clean_errors(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            make_volume(Path(d))
            code, _, err = run("--root", d, "run", "9", "1", "nope")
            self.assertEqual(code, 2)
            self.assertIn("unknown stage", err)
            code, _, err = run("--root", d, "run", "8", "8", "draw")
            self.assertEqual(code, 2)
            self.assertIn("no such volume folder", err)

    def test_a_dead_server_exits_1_not_with_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            make_volume(Path(d))
            import os

            os.environ["GPU_URL"] = "http://127.0.0.1:1"
            self.addCleanup(os.environ.pop, "GPU_URL", None)
            code, out, _ = run("--root", d, "run", "9", "1", "draw")
            self.assertEqual(code, 1)
            self.assertIn("failed", out)


if __name__ == "__main__":
    unittest.main()
