"""Tests for routing (DESIGN.md, Progression, Routing): `doctrine_check.py route`, and the reset trigger
enforced by `triggers --task` and `accept`. Standard library only; each test builds a throwaway git
repository with a small profile, ledger and packet, so no test depends on a consuming project.

Run: python -m unittest discover -s tests
"""
import importlib.util
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
CHECK = Path(os.environ.get("DOCTRINE_CHECK_UNDER_TEST", PLUGIN / "scripts" / "doctrine_check.py"))
ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="test",
    GIT_AUTHOR_EMAIL="test@example.test",
    GIT_COMMITTER_NAME="test",
    GIT_COMMITTER_EMAIL="test@example.test",
)

# Two materially different projects: a web service whose authorization code is never fast, and a
# numerical solver whose solver files are never fast and whose repair budget is larger.
PROFILE_SERVICE = """\
# Doctrine profile: service fixture
- Ledger: `doctrine/ledger.md`
- Lineage audit threshold: 3
- Routing never fast: `src/auth/*`
- Routing reset after: 2
"""
PROFILE_SOLVER = """\
# Doctrine profile: solver fixture
- Ledger: `doctrine/ledger.md`
- Lineage audit threshold: 3
- Routing never fast: `solver/*.py`
- Routing reset after: 3
- Routing probe budget: 1
- Routing consequential words: `tolerance|residual`
"""
PROFILE_OFF = """\
# Doctrine profile: routing off
- Ledger: `doctrine/ledger.md`
- Routing: off
"""

LEDGER_HEAD = """\
# Ledger

| ID | Observation | Status and bound | Consequence and next decision | Tags |
|---|---|---|---|---|
"""

PACKET = """\
# {name}

## Status

{status}

## Lineage

{lineage}

## Repairs

{repairs}

## Criteria

| Id | Behaviour | Check | Oracle |
|---|---|---|---|
| X1 | the behaviour | a-check | spec |

## Readers

None: fixture.
"""


class Repo:
    def __init__(self, profile, rows=(), tasks=None, files=None):
        self.root = Path(tempfile.mkdtemp(prefix="doctrine-route-"))
        self.git("init", "-q")
        (self.root / "doctrine" / "tasks").mkdir(parents=True)
        (self.root / "doctrine" / "profile.md").write_text(profile, encoding="utf-8")
        self.write_ledger(rows)
        for name, (status, lineage, repairs) in (tasks or {}).items():
            (self.root / "doctrine" / "tasks" / f"{name}.md").write_text(
                PACKET.format(name=name, status=status, lineage=lineage, repairs=repairs), encoding="utf-8"
            )
        base = {"src/app.py": "def total(items):\n    count = len(items)\n    return count\n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n"}
        base.update(files or {})
        for path, text in base.items():
            self.write(path, text)
        (self.root / "logs").mkdir()
        (self.root / "logs" / "diagnostic.log").write_text("error: name 'cnt' is not defined\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "fixture")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, env=ENV)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def write_ledger(self, rows):
        body = "".join(f"| {row_id} | obs | status | next | {tags} |\n" for row_id, tags in rows)
        (self.root / "doctrine" / "ledger.md").write_text(LEDGER_HEAD + body, encoding="utf-8")

    def ledger_bytes(self):
        return (self.root / "doctrine" / "ledger.md").read_bytes()

    def run(self, *args):
        result = subprocess.run(
            [sys.executable, str(CHECK), "--root", str(self.root), *args],
            capture_output=True, text=True, env=ENV,
        )
        return result.returncode, result.stdout

    def route(self, *args):
        return self.run("route", *args)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def route_of(output):
    for line in output.splitlines():
        if line.startswith("ROUTE "):
            return line.split()[1]
    return None


class RouteTests(unittest.TestCase):
    def repo(self, *args, **kwargs):
        repo = Repo(*args, **kwargs)
        self.addCleanup(repo.close)
        return repo

    def test_mechanical_rename_is_fast_and_still_confirms(self):
        repo = self.repo(PROFILE_SERVICE)
        repo.write("src/app.py", "def total(items):\n    number = len(items)\n    return number\n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n")
        code, out = repo.route("--action", "mechanical", "--decision", "fix-name", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "fast", out)
        self.assertIn("CONFIRM run the smallest check that covers src/app.py", out)
        self.assertEqual(code, 0)

    def test_formatting_only_is_fast(self):
        repo = self.repo(PROFILE_SERVICE)
        repo.write("src/app.py", "def total(items):\n    count = len( items )\n    return count\n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n")
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "fast", out)

    def test_small_behavioural_changes_never_get_mechanical_privileges(self):
        cases = {
            "a threshold": ("if n > 3:", "if n > 4:", "changes a number"),
            "a condition": ("if n > 3:", "if n >= 3:", "changes an operator"),
            "a literal": ("return True", "return False", "changes an operator, a condition or a literal"),
        }
        for label, (old, new, reason) in cases.items():
            with self.subTest(label):
                repo = self.repo(PROFILE_SERVICE)
                text = (repo.root / "src" / "app.py").read_text(encoding="utf-8").replace(old, new, 1)
                repo.write("src/app.py", text)
                _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
                self.assertEqual(route_of(out), "doctrine", out)
                self.assertIn(reason, out)

    def test_tests_prose_and_protected_paths_are_never_mechanical(self):
        repo = self.repo(PROFILE_SERVICE, files={
            "tests/test_app.py": "assert check(4) is True\n",
            "src/auth/guard.py": "def allowed(user):\n    return user.admin\n",
            "docs/rule.md": "The limit is three.\n",
        })
        repo.write("tests/test_app.py", "assert check(5) is True\n")
        repo.write("src/auth/guard.py", "def allowed(user):\n    return user.admin \n")
        repo.write("docs/rule.md", "The limit is four.\n")
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertIn("tests/test_app.py: changes a test", out)
        self.assertIn("src/auth/guard.py: the profile never lets a change here be fast", out)
        self.assertIn("docs/rule.md: changes prose", out)

    def test_fast_subaction_leaves_the_parent_open(self):
        repo = self.repo(
            PROFILE_SERVICE,
            rows=[("C-1", "kind=defect; state=open; lineage=decision:login")],
            tasks={"login-fix": ("Accepted, 2026-09-27", "decision:login", "C-1")},
        )
        repo.write("src/app.py", "def total(items):\n    number = len(items)\n    return number\n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n")
        before = repo.ledger_bytes()
        code, out = repo.route("--action", "mechanical", "--task", "login-fix", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "fast", out)
        self.assertIn("OPEN login-fix: status 'Accepted'; its criteria, checks and review stay required", out)
        self.assertIn("OPEN C-1: open, repaired only when its criterion passes", out)
        self.assertEqual(repo.ledger_bytes(), before, "routing must not change any record")
        _, done = repo.route("--action", "complete", "--task", "login-fix")
        self.assertEqual(route_of(done), "doctrine", done)
        self.assertIn("completing an investigation accepts nothing", done)

    def test_hard_escalation_cannot_be_suppressed(self):
        rows = [(f"C-{i}", "kind=defect; state=open; lineage=layer:auth") for i in (1, 2, 3)]
        repo = self.repo(PROFILE_SERVICE, rows=rows, tasks={"auth-fix": ("Accepted", "layer:auth", "none")})
        repo.write("src/app.py", "def total(items):\n    count = len(items)\n    return count \n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n")
        code, out = repo.route("--action", "mechanical", "--task", "auth-fix", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertIn("BLOCK audit-due", out)
        self.assertEqual(code, 2)

    def test_inconclusive_probe_escalates_even_after_a_rename(self):
        repo = self.repo(
            PROFILE_SERVICE,
            rows=[("E-1", "kind=probe; lineage=decision:latency; outcome=inconclusive")],
            tasks={"latency-probe-renamed": ("Accepted", "decision:latency", "none")},
        )
        code, out = repo.route("--action", "probe", "--task", "latency-probe-renamed")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertIn("BLOCK probe-exhausted", out)
        self.assertEqual(code, 2)
        _, fresh = repo.route("--action", "probe", "--decision", "another-question")
        self.assertEqual(route_of(fresh), "bounded", fresh)

    def test_decisive_evidence_ends_optional_work(self):
        repo = self.repo(PROFILE_SERVICE, rows=[("E-1", "kind=probe; lineage=decision:cache; outcome=decisive")])
        code, out = repo.route("--action", "investigate", "--decision", "cache")
        self.assertIn("BLOCK answered", out)
        self.assertEqual(code, 2)

    def test_recurring_failed_repair_forces_a_reset_that_must_change_something(self):
        failed = "kind=repair; lineage=decision:flaky; outcome=failed"
        repo = self.repo(
            PROFILE_SERVICE,
            rows=[("E-1", failed), ("E-2", failed)],
            tasks={"flaky-fix": ("Accepted", "decision:flaky", "none")},
        )
        code, out = repo.route("--action", "repair", "--decision", "flaky")
        self.assertEqual(route_of(out), "reset", out)
        self.assertIn("BLOCK reset-due", out)
        self.assertEqual(code, 2)
        code, out = repo.run("triggers", "--task", "flaky-fix")
        self.assertIn("BLOCK reset-due", out, "the command boundary enforces the reset too")
        code, out = repo.run("accept", "flaky-fix")
        self.assertIn("BLOCK reset-due", out)
        repo.write_ledger([("E-1", failed), ("E-2", failed), ("D-1", "kind=reset; lineage=decision:flaky")])
        _, out = repo.route("--action", "repair", "--decision", "flaky")
        self.assertIn("BLOCK reset-due", out, "a reset that changes nothing clears nothing")
        self.assertIn("WARN reset-unchanged", out)
        repo.write_ledger([("E-1", failed), ("E-2", failed), ("D-1", "kind=reset; lineage=decision:flaky; changed=strategy")])
        code, out = repo.route("--action", "repair", "--decision", "flaky")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertEqual(code, 0)
        repo.write_ledger([("E-1", failed), ("E-2", failed), ("D-1", "kind=reset; lineage=decision:flaky; changed=strategy"), ("E-3", failed), ("E-4", failed)])
        _, out = repo.route("--action", "repair", "--decision", "flaky")
        self.assertIn("BLOCK reset-due", out, "the counter is not silently cleared by the first reset")

    def test_new_discriminating_evidence_is_not_repeated_failure(self):
        rows = [
            ("E-1", "kind=repair; lineage=decision:parse; outcome=failed"),
            ("E-2", "kind=repair; lineage=decision:parse; outcome=informative"),
            ("E-3", "kind=repair; lineage=decision:parse; outcome=failed"),
        ]
        repo = self.repo(PROFILE_SERVICE, rows=rows)
        _, out = repo.route("--action", "repair", "--decision", "parse")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertNotIn("reset-due", out)

    def test_changed_configuration_or_state_invalidates_a_delayed_route(self):
        repo = self.repo(PROFILE_SERVICE)
        repo.write("src/app.py", "def total(items):\n    number = len(items)\n    return number\n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n")
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        state = [line.split()[1] for line in out.splitlines() if line.startswith("STATE ")][0]
        (repo.root / "doctrine" / "profile.md").write_text(PROFILE_SERVICE + "- Routing never fast: `src/*`\n", encoding="utf-8")
        code, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log", "--expect-state", state)
        self.assertIn("BLOCK stale-route", out)
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertEqual(code, 2)

    def test_a_stale_cause_is_not_an_established_cause(self):
        repo = self.repo(PROFILE_SERVICE, rows=[("E-1", "kind=result; rests-on=src/app.py; stale=abc1234")])
        repo.write("src/app.py", "def total(items):\n    number = len(items)\n    return number\n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n")
        _, out = repo.route("--action", "mechanical", "--cause", "E-1")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertIn("the cause E-1 is stale", out)

    def test_missing_facts_fall_back_without_changing_state(self):
        repo = self.repo(PROFILE_SERVICE, tasks={"t": ("Accepted", "decision:x", "none")})
        repo.write("src/app.py", "def total(items):\n    number = len(items)\n    return number\n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n")
        before = repo.ledger_bytes()
        code, out = repo.route("--action", "mechanical", "--task", "t")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertIn("no established cause", out)
        self.assertEqual(code, 0)
        self.assertEqual(repo.ledger_bytes(), before)

    def test_rules_only_routing_opens_no_network_connection(self):
        repo = self.repo(PROFILE_SERVICE)
        spec = importlib.util.spec_from_file_location("doctrine_check_under_test", CHECK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = socket.socket

        def refuse(*args, **kwargs):
            raise AssertionError("routing opened a network connection")

        socket.socket = refuse
        try:
            argv = sys.argv
            sys.argv = ["doctrine_check", "--root", str(repo.root), "route", "--action", "probe", "--decision", "q"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as done:
                    module.main()
            self.assertEqual(done.exception.code, 0)
            self.assertIn("ROUTE bounded", buffer.getvalue())
        finally:
            socket.socket = original
            sys.argv = argv

    def test_existing_acceptance_checks_still_run(self):
        repo = self.repo(PROFILE_SERVICE)
        (repo.root / "doctrine" / "tasks" / "bare.md").write_text("# bare\n\n## Status\n\nAccepted\n", encoding="utf-8")
        code, out = repo.run("accept", "bare")
        self.assertIn("BLOCK lineage", out)
        self.assertIn("BLOCK oracle-none", out)
        self.assertEqual(code, 2)

    def test_two_profiles_are_honoured_independently(self):
        failed = "kind=repair; lineage=decision:converge; outcome=failed"
        service = self.repo(PROFILE_SERVICE, rows=[("E-1", failed), ("E-2", failed)])
        solver = self.repo(PROFILE_SOLVER, rows=[("E-1", failed), ("E-2", failed)], files={"solver/step.py": "dt = 0.1\n"})
        _, out = service.route("--action", "repair", "--decision", "converge")
        self.assertEqual(route_of(out), "reset", "the service profile resets after two")
        _, out = solver.route("--action", "repair", "--decision", "converge")
        self.assertEqual(route_of(out), "doctrine", "the solver profile allows a third attempt")
        solver.write("solver/step.py", "dt = 0.1 \n")
        _, out = solver.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertIn("solver/step.py: the profile never lets a change here be fast", out)
        for repo in (service, solver):
            repo.write("src/calc.py", "step = residual_of(x)\n")
            repo.git("add", "src/calc.py")
            repo.git("commit", "-q", "-m", "calc")
            repo.write("src/calc.py", "step = residual_of(y)\n")
        _, out = service.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "fast", "the service profile's terms do not include residual")
        _, out = solver.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertIn("src/calc.py: touches a consequential term", out, "the solver profile's terms do")

    def test_a_trailing_comment_is_not_a_code_change(self):
        repo = self.repo(PROFILE_SERVICE)
        repo.write("src/app.py", "def total(items):\n    count = len(items)  # the item count\n    return count\n\n\ndef check(n):\n    if n > 3:\n        return True\n    return False\n")
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "fast", out)

    def test_routing_off_leaves_the_existing_workflow(self):
        failed = "kind=repair; lineage=decision:converge; outcome=failed"
        repo = self.repo(PROFILE_OFF, rows=[("E-1", failed), ("E-2", failed), ("E-3", failed)], tasks={"t": ("Accepted", "decision:converge", "none")})
        code, out = repo.route("--action", "repair", "--decision", "converge")
        self.assertIn("ROUTE off", out)
        self.assertEqual(code, 0)
        _, out = repo.run("triggers", "--task", "t")
        self.assertNotIn("reset-due", out)


if __name__ == "__main__":
    unittest.main()
