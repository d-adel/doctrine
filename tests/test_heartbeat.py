import subprocess
import unittest

from test_route import ENV, PROFILE_SERVICE, Repo, route_of

BEFORE = "2026-09-01T12:00:00+00:00"
AFTER = "2027-01-01T12:00:00+00:00"
PACKET = "# t\n\n## Status\n\nAccepted\n\n## Lineage\n\ndecision:contact\n\n## Repairs\n\nnone\n\n## Readers\n\nNone: fixture.\n"


def commit(repo, date):
    env = dict(ENV, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(["git", "-C", str(repo.root), "add", "-A"], check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(repo.root), "commit", "-q", "-m", "records"], check=True, capture_output=True, env=env)


def results(start, count, tags="kind=result"):
    return [(f"E-{n}", tags) for n in range(start, start + count)]


class Fixture(unittest.TestCase):
    def repo(self, rows=(), tasks=None):
        repo = Repo(PROFILE_SERVICE, rows=rows)
        self.addCleanup(repo.close)
        for name, text in (tasks or {}).items():
            repo.write(f"doctrine/tasks/{name}.md", text)
        return repo


class HeartbeatDue(Fixture):
    def test_five_counted_rows_since_the_rule_began_need_a_heartbeat(self):
        repo = self.repo()
        four = [("E-1", "kind=result"), ("E-2", "kind=probe; lineage=decision:q; outcome=decisive"),
                ("E-3", "kind=repair; lineage=decision:r; outcome=fixed"), ("E-4", "kind=result")]
        repo.write_ledger(four)
        code, out = repo.run("triggers")
        self.assertNotIn("heartbeat-due", out)
        self.assertEqual(code, 0, out)
        _, out = repo.route("--action", "probe", "--decision", "s")
        self.assertEqual(route_of(out), "bounded", out)
        repo.write_ledger(four + [("E-5", "kind=result")])
        code, out = repo.run("triggers")
        self.assertIn("BLOCK heartbeat-due: 5 result, probe or repair rows (E-1, E-2, E-3, E-4, E-5)", out)
        self.assertEqual(code, 2)
        code, out = repo.route("--action", "probe", "--decision", "s")
        self.assertIn("BLOCK heartbeat-due", out)
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertEqual(code, 2)
        commit(repo, AFTER)
        code, out = repo.run("triggers")
        self.assertIn("BLOCK heartbeat-due", out, "rows committed after the rule began count")

    def test_a_decision_row_needs_a_heartbeat(self):
        repo = self.repo()
        repo.write_ledger([("D-1", "lineage=decision:q")])
        code, out = repo.run("triggers")
        self.assertIn("BLOCK heartbeat-due: decision rows D-1", out)
        self.assertEqual(code, 2)
        repo.write_ledger([("D-1", "lineage=decision:q"), ("H-1", "kind=heartbeat; moved=none")])
        code, out = repo.run("triggers")
        self.assertNotIn("heartbeat-due", out)
        self.assertEqual(code, 0, out)

    def test_rows_count_from_the_commit_that_added_them_not_their_place_in_the_file(self):
        beat = ("H-1", "kind=heartbeat; moved=frame-time")
        repo = self.repo(rows=[beat] + results(1, 6) + [("D-1", "kind=decision")])
        code, out = repo.run("triggers")
        self.assertNotIn("heartbeat-due", out, "rows committed with the heartbeat count before it")
        self.assertEqual(code, 0, out)
        repo.write_ledger(results(7, 4) + results(1, 6) + [("D-1", "kind=decision"), beat])
        _, out = repo.run("triggers")
        self.assertNotIn("heartbeat-due", out)
        commit(repo, AFTER)
        repo.write_ledger(results(7, 5) + results(1, 6) + [("D-1", "kind=decision"), beat])
        code, out = repo.run("triggers")
        self.assertIn("BLOCK heartbeat-due: 5 result, probe or repair rows (E-7, E-8, E-9, E-10, E-11) since the last heartbeat H-1", out)
        self.assertEqual(code, 2)

    def test_an_existing_ledger_is_not_blocked_retroactively(self):
        repo = self.repo()
        old = results(1, 10) + [("D-1", "kind=decision"), ("D-2", "kind=decision")]
        repo.write_ledger(old)
        commit(repo, BEFORE)
        code, out = repo.run("triggers")
        self.assertNotIn("heartbeat-due", out)
        self.assertEqual(code, 0, out)
        _, out = repo.route("--action", "probe", "--decision", "s")
        self.assertEqual(route_of(out), "bounded", out)
        repo.write_ledger(old + results(11, 4))
        _, out = repo.run("triggers")
        self.assertNotIn("heartbeat-due", out)
        repo.write_ledger(old + results(11, 5))
        code, out = repo.run("triggers")
        self.assertIn("BLOCK heartbeat-due: 5 result, probe or repair rows (E-11, E-12, E-13, E-14, E-15)", out)
        self.assertEqual(code, 2)
        repo.write_ledger(old + [("D-3", "kind=decision")])
        _, out = repo.run("triggers")
        self.assertIn("BLOCK heartbeat-due: decision rows D-3", out)

    def test_other_kinds_do_not_count(self):
        repo = self.repo()
        repo.write_ledger(
            [(f"C-{n}", "kind=defect; state=open; lineage=layer:a") for n in (1, 2)]
            + [("O-1", "kind=reference"), ("A-1", "kind=audit; state=done; covers=C-1"),
               ("D-1", "kind=reset; lineage=decision:q; changed=strategy"),
               ("E-1", "kind=representativeness; lineage=decision:q")]
            + results(2, 4)
        )
        code, out = repo.run("triggers")
        self.assertNotIn("heartbeat-due", out)
        self.assertEqual(code, 0, out)


class RouteReview(Fixture):
    def test_two_heartbeats_without_movement_force_a_route_review(self):
        repo = self.repo(rows=[("H-1", "kind=heartbeat; moved=none")])
        repo.write_ledger([("H-1", "kind=heartbeat; moved=none"), ("H-2", "kind=heartbeat; moved=none")])
        code, out = repo.run("triggers")
        self.assertIn("BLOCK route-review: heartbeats H-1 and H-2 both record moved=none", out)
        self.assertEqual(code, 2)
        code, out = repo.route("--action", "repair", "--decision", "contact")
        self.assertIn("BLOCK route-review", out)
        self.assertEqual(code, 2)
        repo.write_ledger([("H-1", "kind=heartbeat; moved=none"), ("H-2", "kind=heartbeat; moved=frame-time")])
        code, out = repo.run("triggers")
        self.assertNotIn("route-review", out)
        self.assertEqual(code, 0, out)
        repo.write_ledger([("H-1", "kind=heartbeat; moved=frame-time"), ("H-2", "kind=heartbeat; moved=none")])
        _, out = repo.run("triggers")
        self.assertNotIn("route-review", out)

    def test_a_heartbeat_without_moved_counts_as_none(self):
        repo = self.repo(rows=[("H-1", "kind=heartbeat"), ("H-2", "kind=heartbeat; moved=none")])
        code, out = repo.run("triggers")
        self.assertIn("WARN heartbeat-moved: heartbeat H-1 has no moved=", out)
        self.assertIn("BLOCK route-review", out)
        self.assertEqual(code, 2)

    def test_a_route_review_clears_it_and_restarts_the_count(self):
        beats = [("H-1", "kind=heartbeat; moved=none"), ("H-2", "kind=heartbeat; moved=none")]
        review = ("D-1", "kind=decision; review=route")
        repo = self.repo(rows=beats)
        repo.write_ledger(beats + [review])
        code, out = repo.run("triggers")
        self.assertNotIn("route-review", out)
        self.assertIn("BLOCK heartbeat-due: decision rows D-1", out, "the review is a decision, so a heartbeat follows it")
        repo.write_ledger(beats + [review, ("H-3", "kind=heartbeat; moved=none")])
        code, out = repo.run("triggers")
        self.assertNotIn("BLOCK", out)
        self.assertEqual(code, 0, out)
        commit(repo, AFTER)
        repo.write_ledger(beats + [review, ("H-3", "kind=heartbeat; moved=none"), ("H-4", "kind=heartbeat; moved=none")])
        code, out = repo.run("triggers")
        self.assertIn("BLOCK route-review: heartbeats H-3 and H-4 both record moved=none", out)
        self.assertEqual(code, 2)

    def test_a_reset_clears_it_and_a_plain_decision_does_not(self):
        beats = [("H-1", "kind=heartbeat; moved=none"), ("H-2", "kind=heartbeat; moved=none")]
        repo = self.repo(rows=beats)
        repo.write_ledger(beats + [("D-1", "kind=reset; lineage=decision:contact; changed=strategy")])
        code, out = repo.run("triggers")
        self.assertNotIn("BLOCK", out)
        self.assertEqual(code, 0, out)
        repo.write_ledger(beats + [("D-1", "kind=decision")])
        _, out = repo.run("triggers")
        self.assertIn("BLOCK route-review", out)


class Representativeness(Fixture):
    def test_a_second_repair_needs_a_representativeness_row(self):
        repair = ("E-1", "kind=repair; lineage=decision:contact; outcome=failed")
        repo = self.repo(tasks={"t": PACKET})
        code, out = repo.route("--action", "repair", "--decision", "contact")
        self.assertNotIn("representativeness-missing", out)
        self.assertEqual(code, 0, out)
        repo.write_ledger([repair])
        code, out = repo.route("--action", "repair", "--decision", "contact")
        self.assertIn("BLOCK representativeness-missing: decision:contact already has repair rows E-1", out)
        self.assertEqual(route_of(out), "doctrine", out)
        self.assertEqual(code, 2)
        code, out = repo.route("--action", "repair", "--task", "t")
        self.assertIn("BLOCK representativeness-missing", out, "the lineage comes from the packet too")
        _, out = repo.route("--action", "probe", "--decision", "contact")
        self.assertNotIn("representativeness-missing", out, "only a repair needs it")
        _, out = repo.route("--action", "repair", "--decision", "other")
        self.assertNotIn("representativeness-missing", out, "another lineage has no repair yet")
        repo.write_ledger([repair, ("E-2", "kind=representativeness; lineage=decision:other")])
        _, out = repo.route("--action", "repair", "--decision", "contact")
        self.assertIn("BLOCK representativeness-missing", out, "another lineage's row does not count")
        repo.write_ledger([repair, ("E-2", "kind=representativeness; lineage=decision:contact")])
        code, out = repo.route("--action", "repair", "--decision", "contact")
        self.assertNotIn("representativeness-missing", out)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
