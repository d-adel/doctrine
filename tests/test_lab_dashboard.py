import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab import dashboard
from lab.store import Store

SCOREBOARD = {"recipe": "pile", "metric": "stepMsMean", "target": 8.0, "more": ["stepMsP95", "stepMsMax"]}


def sha(mark):
    return (mark * 40)[:40]


def finish(store, commit, metrics, finished, exit_code=0, recipe="pile", cls="gate"):
    job_id = store.submit(recipe, {}, commit, [], cls, False, now=finished - 10)
    store.claim("bench", [], now=finished - 5)
    store.finish(job_id, "bench", exit_code, {"metrics": metrics}, now=finished)
    return job_id


def section(page, title):
    start = page.index(f"<h2>{title}")
    end = page.find("<h2>", start + 4)
    return page[start:end if end >= 0 else len(page)]


class Scoreboard(unittest.TestCase):
    def setUp(self):
        self.lab = SimpleNamespace(store=Store(":memory:"), config={"scoreboard": dict(SCOREBOARD)})

    def render(self):
        return dashboard.render(self.lab, "token")

    def test_done_runs_of_the_recipe_newest_first_with_their_change(self):
        store = self.lab.store
        finish(store, sha("a"), {"stepMsMean": 12.0, "stepMsP95": 14.0, "stepMsMax": 20.0}, 100.0)
        finish(store, sha("b"), {"stepMsMean": 10.0, "stepMsP95": 13.5, "stepMsMax": 19.0}, 200.0)
        finish(store, sha("c"), {"stepMsMean": 10.5, "stepMsP95": 13.0, "stepMsMax": 18.25}, 300.0)
        finish(store, sha("d"), {"stepMsMean": 1.0}, 400.0, exit_code=1)
        finish(store, sha("e"), {"stepMsMean": 2.0}, 500.0, recipe="other")
        board = section(self.render(), "Scoreboard")
        self.assertLess(board.index("cccccccc"), board.index("bbbbbbbb"))
        self.assertLess(board.index("bbbbbbbb"), board.index("aaaaaaaa"))
        self.assertNotIn("dddddddd", board)
        self.assertNotIn("eeeeeeee", board)
        self.assertNotIn("c" * 9, board)
        for text in ("+0.5", "-2", "18.25", "13.5", "stepMsP95", "stepMsMax",
                     time.strftime("%Y-%m-%d %H:%M", time.localtime(300.0))):
            self.assertIn(text, board)
        self.assertEqual(board.count("<td>8</td>"), 3)

    def test_the_newest_value_stands_large_with_its_ratio_to_the_target(self):
        finish(self.lab.store, sha("a"), {"stepMsMean": 12.0}, 100.0)
        finish(self.lab.store, sha("b"), {"stepMsMean": 10.0}, 200.0)
        board = section(self.render(), "Scoreboard")
        self.assertIn("class='score'>10<", board)
        self.assertIn("1.25", board)

    def test_only_the_last_twenty_runs_show(self):
        for index in range(25):
            finish(self.lab.store, f"{index:08x}" + "0" * 32, {"stepMsMean": 9.0 + index}, 100.0 + index)
        board = section(self.render(), "Scoreboard")
        self.assertEqual(board.count("<tr>"), 21)
        self.assertNotIn("00000004", board)
        self.assertIn("00000005", board)

    def test_the_newest_finished_run_leads_whatever_its_id(self):
        store = self.lab.store
        first = store.submit("pile", {}, sha("a"), [], "gate", False, now=1.0)
        second = store.submit("pile", {}, sha("b"), [], "gate", False, now=1.0)
        store.claim("one", [], now=2.0)
        store.claim("two", [], now=2.0)
        store.finish(second, "two", 0, {"metrics": {"stepMsMean": 9.0}}, now=3.0)
        store.finish(first, "one", 0, {"metrics": {"stepMsMean": 11.0}}, now=4.0)
        self.assertEqual([job["id"] for job in store.done("pile", 20)], [first, second])

    def test_everything_in_the_scoreboard_is_escaped(self):
        self.lab.config["scoreboard"]["more"] = ["<i>more</i>"]
        finish(self.lab.store, sha("a"), {"stepMsMean": 9.0, "<i>more</i>": "<b>x</b>"}, 100.0)
        board = section(self.render(), "Scoreboard")
        self.assertNotIn("<b>x</b>", board)
        self.assertNotIn("<i>more</i>", board)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", board)

    def test_no_run_yet_still_renders(self):
        board = section(self.render(), "Scoreboard")
        self.assertIn("no runs yet", board)

    def test_the_scoreboard_comes_before_the_machines(self):
        page = self.render()
        self.assertLess(page.index("<h2>Scoreboard"), page.index("<h2>Machines"))

    def test_no_scoreboard_config_shows_none(self):
        self.lab.config = {}
        self.assertNotIn("Scoreboard", self.render())


class PlanBanner(unittest.TestCase):
    def setUp(self):
        self.lab = SimpleNamespace(store=Store(":memory:"), config={})
        self.now = time.time()

    def banner(self):
        page = dashboard.render(self.lab, "token")
        if "Plan empty" not in page:
            return None
        start = page.index("<body>") + len("<body>")
        self.assertTrue(page[start:].startswith("<div class='plan'>"))
        return page[start:page.index("</div>", start)]

    def running(self, worker, cls, claimed, beat=None):
        job_id = self.lab.store.submit("r", {}, sha("a"), [], cls, False, now=claimed)
        self.lab.store.claim(worker, [], now=claimed)
        if beat is not None:
            self.lab.store.heartbeat(job_id, worker, now=beat)
        return job_id

    def test_idle_machines_raise_the_banner_and_are_named(self):
        self.lab.store.touch_worker("spare", [], now=self.now)
        self.lab.store.touch_worker("<desk>", [], now=self.now)
        banner = self.banner()
        self.assertIn("spare", banner)
        self.assertIn("&lt;desk&gt;", banner)

    def test_machines_running_sweeps_leave_the_plan_empty(self):
        self.lab.store.touch_worker("spare", [], now=self.now)
        self.running("desktop", "sweep", self.now)
        banner = self.banner()
        self.assertIn("desktop", banner)
        self.assertIn("spare", banner)

    def test_a_planned_job_clears_the_banner(self):
        self.lab.store.touch_worker("spare", [], now=self.now)
        self.running("desktop", "gate", self.now)
        self.assertIsNone(self.banner())

    def test_a_long_planned_job_still_heartbeating_clears_the_banner(self):
        self.lab.store.touch_worker("spare", [], now=self.now)
        self.running("desktop", "experiment", self.now - 600, beat=self.now - 5)
        self.assertIsNone(self.banner())

    def test_machines_not_seen_for_two_minutes_are_left_out(self):
        self.lab.store.touch_worker("spare", [], now=self.now - 200)
        self.lab.store.touch_worker("desktop", [], now=self.now)
        banner = self.banner()
        self.assertIn("desktop", banner)
        self.assertNotIn("spare", banner)

    def test_no_machine_seen_shows_no_banner(self):
        self.lab.store.touch_worker("spare", [], now=self.now - 200)
        self.assertIsNone(self.banner())


if __name__ == "__main__":
    unittest.main()
