import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
CHECK = PLUGIN / "scripts" / "doctrine_check.py"
ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="test",
    GIT_AUTHOR_EMAIL="test@example.test",
    GIT_COMMITTER_NAME="test",
    GIT_COMMITTER_EMAIL="test@example.test",
)

PROFILE = """\
# Doctrine profile: model fixture
- Ledger: `doctrine/ledger.md`
- Model: `doctrine/model.md`
"""

LEDGER = """\
# Ledger

| ID | Observation | Status and bound | Consequence and next decision | Tags |
|---|---|---|---|---|
| E-1 | a measurement | measured | none | layer:solver |
"""

MODEL = """\
# Model

## Goal

| Term | Target | Measured now | Gap | Source |
|---|---|---|---|---|
| burst frames, p99 | 50 ms | 137 ms | 2.7x | E-1 |
| frames without a promotion, median | 8 ms | 2 ms | met | E-1 |

## Routes

| Route | Bound at milestone scale | Status |
|---|---|---|
| gpu windows | about 137 ms a burst frame | falsified as planned, 2.7x (E-1) |
| fewer windows | unknown | open: needs a reset |
| cheaper window-frames | about 40 ms a burst frame | open |

## Next

1. The reset (moves: burst frames, p99).
"""

PACKET = """\
# {name}

## Status

Draft, 2026-10-02

## Moves

M-1. {predicts}

{route}
## Lineage

layer:solver

## Criteria

| Id | Behaviour | Check | Oracle |
|---|---|---|---|
| C1 | it works | the suite | spec |

## Readers

None: the packet changes no name.
"""


class ModelRules(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="doctrine-model-"))
        (self.root / "doctrine" / "tasks").mkdir(parents=True)
        self.write("doctrine/profile.md", PROFILE)
        self.write("doctrine/ledger.md", LEDGER)
        self.write("doctrine/model.md", MODEL)
        self.git("init", "--quiet", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "fixture")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(textwrap.dedent(text))

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, env=ENV, capture_output=True, text=True, check=True).stdout

    def check(self, *args):
        result = subprocess.run([sys.executable, str(CHECK), "--root", str(self.root), *args],
                                capture_output=True, text=True, env=ENV)
        return result.returncode, result.stdout + result.stderr

    def packet(self, route="## Route\n\ncheaper window-frames\n", predicts="Predicts: burst frames, p99: 137 ms -> 45 ms"):
        self.write("doctrine/tasks/step.md", PACKET.format(name="step", route=route, predicts=predicts))

    def test_a_packet_on_an_open_bounded_route_with_a_prediction_passes_the_model_checks(self):
        self.packet()
        code, out = self.check("accept", "step")
        for word in ("route-", "prediction-", "model"):
            self.assertNotIn(f"BLOCK {word}", out)

    def test_a_packet_without_a_route_is_refused(self):
        self.packet(route="")
        code, out = self.check("accept", "step")
        self.assertNotEqual(code, 0)
        self.assertIn("BLOCK route-none", out)

    def test_a_packet_on_a_falsified_route_is_refused(self):
        self.packet(route="## Route\n\ngpu windows\n")
        code, out = self.check("accept", "step")
        self.assertNotEqual(code, 0)
        self.assertIn("BLOCK route-falsified", out)

    def test_a_packet_on_a_route_without_a_bound_is_refused(self):
        self.packet(route="## Route\n\nfewer windows\n")
        code, out = self.check("accept", "step")
        self.assertNotEqual(code, 0)
        self.assertIn("BLOCK route-unbounded", out)

    def test_a_packet_naming_no_model_route_is_refused(self):
        self.packet(route="## Route\n\nsomething else\n")
        code, out = self.check("accept", "step")
        self.assertIn("BLOCK route-unknown", out)

    def test_a_packet_without_a_prediction_is_refused(self):
        self.packet(predicts="It helps.")
        code, out = self.check("accept", "step")
        self.assertIn("BLOCK prediction-none", out)

    def test_a_prediction_must_name_a_goal_term(self):
        self.packet(predicts="Predicts: commit count: 3 -> 9")
        code, out = self.check("accept", "step")
        self.assertIn("BLOCK prediction-term", out)

    def test_a_result_staged_without_the_model_is_refused(self):
        self.write("doctrine/ledger.md", LEDGER + "| E-2 | another | measured | none | layer:solver |\n")
        self.git("add", "doctrine/ledger.md")
        code, out = self.check("model", "--staged")
        self.assertNotEqual(code, 0)
        self.assertIn("BLOCK model-stale", out)

    def test_a_result_staged_with_the_model_passes(self):
        self.write("doctrine/ledger.md", LEDGER + "| E-2 | another | measured | none | layer:solver |\n")
        self.write("doctrine/model.md", MODEL + "\nE-2 changes nothing.\n")
        self.git("add", "-A")
        code, out = self.check("model", "--staged")
        self.assertEqual(code, 0, out)

    def test_a_commit_range_with_a_result_and_no_model_change_is_refused(self):
        base = self.git("rev-parse", "HEAD").strip()
        self.write("doctrine/ledger.md", LEDGER + "| E-2 | another | measured | none | layer:solver |\n")
        self.git("commit", "--quiet", "-am", "a result")
        code, out = self.check("model", "--base", base, "--head", "HEAD")
        self.assertIn("BLOCK model-stale", out)

    def test_an_empty_plan_is_refused(self):
        self.write("doctrine/model.md", MODEL.replace("1. The reset (moves: burst frames, p99).\n", ""))
        code, out = self.check("model")
        self.assertNotEqual(code, 0)
        self.assertIn("BLOCK plan-empty", out)

    def test_a_next_item_must_name_the_term_it_moves(self):
        self.write("doctrine/model.md", MODEL.replace("(moves: burst frames, p99)", "(soon)"))
        code, out = self.check("model")
        self.assertIn("BLOCK next-moves", out)

    def test_a_next_item_may_name_its_term_on_a_continuation_line(self):
        self.write("doctrine/model.md", MODEL.replace("1. The reset (moves: burst frames, p99).",
                                                      "1. The reset, from the model" + chr(10) + "   (moves: burst frames, p99)."))
        code, out = self.check("model")
        self.assertEqual(code, 0, out)

    def test_a_project_without_a_model_line_is_not_checked(self):
        self.write("doctrine/profile.md", PROFILE.replace("- Model: `doctrine/model.md`\n", ""))
        self.packet(route="", predicts="It helps.")
        code, out = self.check("accept", "step")
        self.assertNotIn("BLOCK route-none", out)
        self.assertNotIn("BLOCK prediction-none", out)


if __name__ == "__main__":
    unittest.main()
