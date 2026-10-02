import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab import recipes

BOOK = {
    "recipes": {
        "check-line": {"short": True, "params": {"name": ""}, "run": "bash doctrine/round.sh one . \"$LAB_LOGDIR\" \"{name}\""},
        "pile": {"params": {"bodies": "500"}, "run": "run-pile {bodies}",
                 "metrics": {"stepMsMean": "stepMsMean ([0-9.eE+-]+)", "case": "case (\\w+)"}},
        "sweep-windows": {"needs": ["os=windows"], "fanout": {
            "file": "doctrine/blocking.md", "recipe": "check-line", "param": "name", "needs": ["os=windows"],
            "pattern": "^- (?P<value>[^\\[\\n]+?)(?: \\[(?!venue)[^\\]]*\\])* :: "}},
        "sweep-linux": {"needs": ["os=linux"], "fanout": {
            "file": "doctrine/blocking.md", "recipe": "check-line", "param": "name", "needs": ["os=linux"],
            "pattern": "^- (?P<value>[^\\[\\n]+?)(?: \\[[^\\]]*\\])* \\[venue: linux\\](?: \\[[^\\]]*\\])* :: "}},
    }
}

BLOCKING = """# Blocking

- module tiers :: cmake --preset dev
- suite :: ctest --preset dev
- build release [tier: background] :: cmake --preset release
- linux build [venue: linux] :: cmake --preset dev && cmake --build build-dev
- linux suite [venue: linux] :: ctest --preset dev
"""


class Recipes(unittest.TestCase):
    def setUp(self):
        self.book = recipes.load(json.dumps(BOOK))

    def test_load_refuses_a_recipe_with_both_run_and_fanout(self):
        with self.assertRaises(ValueError):
            recipes.load(json.dumps({"recipes": {"x": {"run": "a", "fanout": {}}}}))

    def test_load_refuses_a_metric_without_a_group(self):
        with self.assertRaises(ValueError):
            recipes.load(json.dumps({"recipes": {"x": {"run": "a", "metrics": {"m": "no group"}}}}))

    def test_load_refuses_a_fanout_to_a_missing_recipe(self):
        with self.assertRaises(ValueError):
            recipes.load(json.dumps({"recipes": {"x": {"fanout": {"file": "f", "pattern": "(?P<value>.)",
                                                                  "recipe": "y", "param": "p"}}}}))

    def test_command_fills_parameters_and_defaults(self):
        self.assertEqual(recipes.command(self.book["pile"], {}), "run-pile 500")
        self.assertEqual(recipes.command(self.book["pile"], {"bodies": "40"}), "run-pile 40")
        self.assertEqual(recipes.command(self.book["check-line"], {"name": "build dev"}),
                         'bash doctrine/round.sh one . "$LAB_LOGDIR" "build dev"')

    def test_command_refuses_shell_characters(self):
        for value in ('a"; rm -rf ~', "$(id)", "a`b`", "a;b", "a|b", "a&b", "a'b", "a\\b"):
            with self.assertRaises(ValueError):
                recipes.command(self.book["check-line"], {"name": value})

    def test_command_refuses_a_trailing_newline(self):
        with self.assertRaises(ValueError):
            recipes.command(self.book["check-line"], {"name": "a" + chr(10)})

    def test_command_refuses_an_undeclared_parameter(self):
        with self.assertRaises(ValueError):
            recipes.command(self.book["pile"], {"seed": "1"})

    def test_fanout_splits_the_blocking_lines_by_venue(self):
        windows = [child["params"]["name"] for child in recipes.fanout(self.book["sweep-windows"], BLOCKING)]
        linux = [child["params"]["name"] for child in recipes.fanout(self.book["sweep-linux"], BLOCKING)]
        self.assertEqual(windows, ["module tiers", "suite", "build release"])
        self.assertEqual(linux, ["linux build", "linux suite"])
        self.assertEqual(recipes.fanout(self.book["sweep-linux"], BLOCKING)[0]["needs"], ["os=linux"])

    def test_metrics_take_the_last_match(self):
        output = "stepMsMean 9.5\ncase P3\nstepMsMean 8.25\n"
        self.assertEqual(recipes.metrics(self.book["pile"], output), {"stepMsMean": 8.25, "case": "P3"})


if __name__ == "__main__":
    unittest.main()
