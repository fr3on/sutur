import unittest

from sutur_pipeline.config import Settings
from sutur_pipeline.errors import ConfigError, GraphError
from sutur_pipeline.pipeline import order
from sutur_pipeline.tasks.base import Context, Result, Task
from sutur_pipeline.tasks.registry import Registry


def task(name: str, *requires: str) -> Task:
    class A(Task):
        def run(self, ctx: Context) -> Result:
            return Result.success("ok")

    A.name, A.requires = name, tuple(requires)
    return A()


def registry(*tasks: Task) -> Registry:
    r = Registry()
    for a in tasks:
        r.add(a)
    return r


class GraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.r = registry(task("draw"), task("scan", "draw"), task("pdf", "scan"))

    def test_prerequisites_come_first_whatever_the_given_order(self) -> None:
        self.assertEqual(order(["pdf", "draw", "scan"], self.r), ["draw", "scan", "pdf"])

    def test_unselected_prerequisites_are_assumed_done(self) -> None:
        self.assertEqual(order(["pdf"], self.r), ["pdf"])

    def test_with_deps_pulls_them_in(self) -> None:
        self.assertEqual(order(["pdf"], self.r, with_deps=True), ["draw", "scan", "pdf"])

    def test_duplicates_are_dropped(self) -> None:
        self.assertEqual(order(["draw", "draw"], self.r), ["draw"])

    def test_unknown_stage(self) -> None:
        with self.assertRaisesRegex(GraphError, "unknown stage 'nope'"):
            order(["nope"], self.r)

    def test_cycle(self) -> None:
        r = registry(task("a", "b"), task("b", "a"))
        with self.assertRaisesRegex(GraphError, "loop"):
            order(["a", "b"], r)

    def test_duplicate_names_are_refused(self) -> None:
        with self.assertRaises(GraphError):
            registry(task("x"), task("x"))


class ConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        s = Settings.from_env({})
        self.assertEqual(s.image_urls, ("http://localhost:8000",))
        self.assertEqual(s.scan_rounds, 3)

    def test_gpu_urls_list_wins_over_single_url(self) -> None:
        s = Settings.from_env({"GPU_URLS": "http://a:1/, http://b:2", "GPU_URL": "http://z"})
        self.assertEqual(s.image_urls, ("http://a:1", "http://b:2"))

    def test_bad_number(self) -> None:
        with self.assertRaises(ConfigError):
            Settings.from_env({"VL_THREADS": "many"})
        with self.assertRaises(ConfigError):
            Settings.from_env({"SCAN_ROUNDS": "0"})

    def test_key_is_not_in_repr(self) -> None:
        self.assertNotIn("secret", repr(Settings.from_env({"UNSLOTH_API_KEY": "secret"})))


if __name__ == "__main__":
    unittest.main()


class NegativePromptTests(unittest.TestCase):
    def test_default_negative_is_the_one_the_old_tools_sent(self) -> None:
        old = ("tall ship, square-rigged ship, galleon, pirate ship, three masts, speech bubble, text balloon, signboard with writing, microphone, modern object, "
               "glasses, wristwatch, mobile phone, camera, electric lamp, neon, plastic, mirror reflection, blurry, low quality, deformed face, extra people, "
               "color, watermark, signature, text, letters, numbers")
        self.assertEqual(Settings.from_env({}).negative_prompt, old)
        self.assertEqual(Settings.from_env({"DRAW_NEGATIVE": "x"}).negative_prompt, "x")
