"""A short replay of real decision points, reconstructed as minimal fixtures, plus labelled synthetic
cases. Each uses only what was known at the original decision point. It is a regression check and a
pilot, not proof of general safety.

Historical cases (H) come from one consuming project's campaign on 2026-09-27; the fixtures keep the
shape of each change, not its code. Synthetic cases (S) are labelled as such.
"""
import unittest

from test_route import PROFILE_SERVICE, Repo, route_of

PACKET_CHECKS = "# p\n\n## Checks\n\n- web-shape :: cd platform && echo \"the live responses have the fixture's shape\"\n"
POLICY = "create policy note_owner_closed_insert on ledger.note\n  with check (c.xmin = pg_current_xact_id()::xid and c.closed_at is not null);\n"
READINESS = "export function summaryFigure(entry) {\n  return entry ? entry.statement : null;\n}\n"
SCAN = "const SCAN_TIMEOUT_MS = 60000;\n"


class Replay(unittest.TestCase):
    def repo(self, **kwargs):
        repo = Repo(PROFILE_SERVICE, **kwargs)
        self.addCleanup(repo.close)
        return repo

    def test_h1_a_check_line_typo_is_not_mechanical(self):
        # A packet's check line ended with a stray backslash; the fix was one character in markdown.
        # A check line is executable, so routing keeps it on the doctrine route: the packet's gate runs.
        repo = self.repo(files={"doctrine/tasks/p.md": PACKET_CHECKS.replace('shape"\n', 'shape\\"\n')})
        repo.write("doctrine/tasks/p.md", PACKET_CHECKS)
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertIn("changes prose", out)

    def test_h2_a_lone_timeout_gets_one_rerun_then_the_reasoning_path(self):
        # A whole-database scan timed out at a gate under load. The rule then was: re-run it alone once.
        repo = self.repo()
        _, out = repo.route("--action", "probe", "--decision", "s3-scan-timeout")
        self.assertEqual(route_of(out), "bounded", out)
        repo.write_ledger([("E-1", "kind=probe; lineage=decision:s3-scan-timeout; outcome=inconclusive")])
        code, out = repo.route("--action", "probe", "--decision", "s3-scan-timeout")
        self.assertIn("BLOCK probe-exhausted", out)
        self.assertEqual(code, 2)

    def test_h3_a_ui_that_computes_a_figure_is_a_behavioural_repair(self):
        # A review found the UI computing a figure the API declines to compute.
        repo = self.repo(files={"platform/web/src/lib/readiness.ts": READINESS})
        repo.write("platform/web/src/lib/readiness.ts", READINESS.replace("entry ? entry.statement : null", "entry ? entry.done / entry.required : null"))
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "doctrine", out)

    def test_h4_one_clause_in_an_authorization_policy_is_never_fast(self):
        # A review found an insert policy accepting a no-op re-stamp; the fix added one clause.
        repo = self.repo(files={"platform/db/migrations/0023_x.sql": POLICY})
        repo.write("platform/db/migrations/0023_x.sql", POLICY.replace("is not null);", "is not null and c.closed_at = now());"))
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertIn("changes an operator", out)

    def test_h7_the_same_class_of_miss_repaired_twice_forces_a_reset(self):
        # Packets repeatedly missed exact-set tests; each amendment was a repair cycle on one decision.
        failed = "kind=repair; lineage=decision:exact-set-pins; outcome=failed"
        repo = self.repo(rows=[("E-1", failed), ("E-2", failed)])
        code, out = repo.route("--action", "repair", "--decision", "exact-set-pins")
        self.assertEqual(route_of(out), "reset", out)
        self.assertEqual(code, 2)

    def test_s1_synthetic_misspelled_identifier_with_a_diagnostic_is_fast(self):
        repo = self.repo(files={"src/tally.py": "def tally(xs):\n    totl = sum(xs)\n    return totl\n"})
        repo.write("src/tally.py", "def tally(xs):\n    total = sum(xs)\n    return total\n")
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "fast", out)

    def test_s2_synthetic_raising_a_timeout_to_get_a_test_through_is_not_mechanical(self):
        repo = self.repo(files={"platform/test/scan.test.ts": SCAN, "src/scan.ts": SCAN})
        repo.write("src/scan.ts", SCAN.replace("60000", "120000"))
        _, out = repo.route("--action", "mechanical", "--cause", "logs/diagnostic.log")
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertIn("changes a number", out)


if __name__ == "__main__":
    unittest.main()
