import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from labfixture import Coordinator, Repo, recipe_file
from lab import server

BOOK = {
    "say": {"short": True, "params": {"word": "hi"}, "run": "echo {word}", "metrics": {"answer": "answer ([0-9]+)"}},
    "check-line": {"short": True, "params": {"name": ""}, "run": "echo \"{name}\""},
    "sweep-linux": {"needs": ["os=linux"], "fanout": {"file": "doctrine/blocking.md", "recipe": "check-line",
                                                      "param": "name", "needs": ["os=linux"],
                                                      "pattern": "^- (?P<value>[^\\[\\n]+?) :: "}},
    "bench": {"needs": ["reference"], "run": "echo bench", "metrics": {"stepMsMean": "stepMsMean ([0-9.]+)"}},
}
BLOCKING = "- one :: true\n- two :: true\n"
LINUX = {"label": "os=linux", "recipe": "sweep-linux", "ref": "main", "when": "code"}
RECORDS = ["doctrine/**", "*.md"]


class Api(unittest.TestCase):
    def setUp(self):
        files = recipe_file(BOOK)
        files["doctrine/blocking.md"] = BLOCKING
        self.repo = Repo(files)
        self.lab = Coordinator(self.repo, idle=[LINUX], records=RECORDS)
        self.client = self.lab.client

    def tearDown(self):
        self.lab.close()
        self.repo.close()

    def test_a_request_without_the_token_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(self.lab.url + "/api/jobs")
        self.assertEqual(caught.exception.code, 401)

    def test_the_dashboard_needs_the_token_unless_it_is_public(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(self.lab.url + "/")
        self.assertEqual(caught.exception.code, 401)
        self.lab.lab.config["public_dashboard"] = True
        page = urllib.request.urlopen(self.lab.url + "/").read().decode()
        self.assertIn("Machines", page)
        self.assertNotIn("<button>", page)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(self.lab.url + "/api/jobs")
        self.assertEqual(caught.exception.code, 401)

    def test_submit_claim_log_finish_round_trip(self):
        [job_id] = self.client.submit("say", self.repo.head, {"word": "there"}, "gate")
        job = self.client.claim("desktop", ["os=windows"])
        self.assertEqual(job["id"], job_id)
        self.assertEqual(job["command"], "echo there")
        self.assertTrue(self.client.heartbeat(job_id, "desktop"))
        self.client.append_log(job_id, b"answer 42\n")
        self.assertEqual(self.client.log(job_id), b"answer 42\n")
        self.assertTrue(self.client.finish(job_id, "desktop", 0, {"machine": "desktop"}))
        finished = self.client.job(job_id)
        self.assertEqual(finished["state"], "done")
        self.assertEqual(finished["result"]["metrics"], {"answer": 42.0})

    def test_a_refused_parameter_answers_400(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.client.submit("say", self.repo.head, {"word": "$(id)"}, "gate")
        self.assertEqual(caught.exception.code, 400)

    def test_an_unknown_recipe_answers_400(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.client.submit("nothing", self.repo.head, {}, "gate")

    def test_a_fanout_submits_one_job_per_line(self):
        ids = self.client.submit("sweep-linux", self.repo.head, {}, "sweep")
        self.assertEqual(len(ids), 2)
        self.assertEqual([self.client.job(job_id)["params"]["name"] for job_id in ids], ["one", "two"])
        self.assertEqual(self.client.job(ids[0])["needs"], ["os=linux"])

    def test_an_idle_linux_worker_sweeps_main_once(self):
        first = self.client.claim("spare", ["os=linux"])
        self.assertEqual(first["recipe"], "check-line")
        self.assertEqual(first["commit_sha"], self.repo.head)
        self.assertEqual(first["for_ref"], f"idle:os=linux:sweep-linux:main:code:{self.repo.head}")
        self.client.finish(first["id"], "spare", 0, {})
        second = self.client.claim("spare", ["os=linux"])
        self.client.finish(second["id"], "spare", 0, {})
        self.assertIsNone(self.client.claim("spare", ["os=linux"]))

    def test_a_new_main_head_is_swept_again(self):
        for _ in range(2):
            job = self.client.claim("spare", ["os=linux"])
            self.client.finish(job["id"], "spare", 0, {})
        newer = self.repo.commit({"note.txt": "x"})
        self.assertEqual(self.client.claim("spare", ["os=linux"])["commit_sha"], newer)

    def test_a_worker_without_an_idle_label_gets_nothing(self):
        self.assertIsNone(self.client.claim("desktop", ["os=windows"]))

    def test_a_paused_worker_is_not_given_a_sweep(self):
        self.client.pause("spare", True)
        self.assertIsNone(self.client.claim("spare", ["os=linux"]))
        self.assertEqual(self.client.jobs(), [])

    def test_cancel_through_the_api(self):
        [job_id] = self.client.submit("say", self.repo.head, {}, "gate")
        self.assertTrue(self.client.cancel(job_id))
        self.assertEqual(self.client.job(job_id)["state"], "cancelled")

    def test_the_dashboard_lists_workers_and_jobs(self):
        self.client.submit("say", self.repo.head, {}, "gate")
        self.client.claim("desktop", ["os=windows"])
        page = urllib.request.urlopen(f"{self.lab.url}/?token={self.lab.token}").read().decode()
        self.assertIn("desktop", page)
        self.assertIn("say", page)
        self.assertIn("gate", page)

    def test_the_dashboard_shows_each_idle_rule(self):
        self.client.claim("spare", ["os=linux"])
        page = urllib.request.urlopen(f"{self.lab.url}/?token={self.lab.token}").read().decode()
        self.assertIn("sweep-linux", page)
        self.assertIn(self.repo.head[:8], page)
        self.assertIn("1 queued, 1 running", page)


class IdleRules(unittest.TestCase):
    def start(self, rules):
        files = recipe_file(BOOK)
        files["doctrine/blocking.md"] = BLOCKING
        files["src/a.cpp"] = "int a = 1;\n"
        self.repo = Repo(files)
        self.addCleanup(self.repo.close)
        self.lab = Coordinator(self.repo, idle=rules, records=RECORDS)
        self.addCleanup(self.lab.close)
        self.moment = [1000.0]
        self.lab.lab.clock = lambda: self.moment[0]
        return self.lab.client

    def drain(self, worker, labels):
        claimed = []
        job = self.lab.client.claim(worker, labels)
        while job:
            self.lab.client.finish(job["id"], worker, 0, {})
            claimed.append(job)
            job = self.lab.client.claim(worker, labels)
        return claimed

    def test_a_commit_touching_only_records_is_not_swept(self):
        client = self.start([LINUX])
        self.assertEqual(len(self.drain("spare", ["os=linux"])), 2)
        self.repo.commit({"doctrine/notes/today.md": "x\n", "doctrine/a/b/c.txt": "y\n", "README.md": "z\n",
                          "src/notes.md": "w\n"})
        self.assertIsNone(client.claim("spare", ["os=linux"]))
        self.assertEqual(len(client.jobs()), 2)
        self.assertEqual(self.lab.lab.store.idle_mark(server.Lab.rule_name(LINUX))["head"], self.repo.head)

    def test_code_after_a_records_only_head_is_swept(self):
        client = self.start([LINUX])
        self.drain("spare", ["os=linux"])
        self.repo.commit({"doctrine/notes.md": "x\n"})
        self.assertIsNone(client.claim("spare", ["os=linux"]))
        self.repo.commit({"src/b.cpp": "int b;\n"})
        self.assertEqual(client.claim("spare", ["os=linux"])["commit_sha"], self.repo.head)

    def test_a_code_change_behind_a_records_commit_is_swept(self):
        client = self.start([LINUX])
        self.drain("spare", ["os=linux"])
        self.repo.commit({"src/a.cpp": "int a = 2;\n"})
        self.repo.commit({"doctrine/notes.md": "x\n"})
        self.assertEqual(client.claim("spare", ["os=linux"])["commit_sha"], self.repo.head)

    def test_a_file_renamed_into_records_counts_its_old_path(self):
        client = self.start([LINUX])
        self.drain("spare", ["os=linux"])
        (self.repo.work / "src" / "a.cpp").unlink()
        self.repo.commit({"doctrine/a.cpp": "int a = 1;\n"})
        self.assertEqual(client.claim("spare", ["os=linux"])["commit_sha"], self.repo.head)

    def test_a_daily_rule_runs_at_most_once_a_day(self):
        client = self.start([dict(LINUX, when="daily")])
        self.assertEqual(len(self.drain("spare", ["os=linux"])), 2)
        self.repo.commit({"src/b.cpp": "int b;\n"})
        self.moment[0] += 23 * 3600
        self.assertIsNone(client.claim("spare", ["os=linux"]))
        self.moment[0] += 3600 + 1
        self.assertEqual({job["commit_sha"] for job in self.drain("spare", ["os=linux"])}, {self.repo.head})

    def test_a_daily_rule_does_not_run_a_head_twice(self):
        client = self.start([dict(LINUX, when="daily")])
        self.drain("spare", ["os=linux"])
        self.moment[0] += 3 * 86400
        self.assertIsNone(client.claim("spare", ["os=linux"]))
        self.assertEqual(len(client.jobs()), 2)

    def test_the_first_rule_that_queues_wins(self):
        bench = {"label": "reference", "recipe": "bench", "ref": "main", "when": "code"}
        client = self.start([bench, dict(LINUX, when="daily")])
        labels = ["os=linux", "reference"]
        first = client.claim("desktop", labels)
        self.assertEqual(first["recipe"], "bench")
        self.assertEqual(len(client.jobs()), 1)
        client.finish(first["id"], "desktop", 0, {})
        self.assertEqual(client.claim("desktop", labels)["recipe"], "check-line")

    def test_a_rule_passes_over_a_worker_without_its_label(self):
        bench = {"label": "reference", "recipe": "bench", "ref": "main", "when": "code"}
        client = self.start([bench, LINUX])
        self.assertEqual(client.claim("spare", ["os=linux"])["recipe"], "check-line")
        self.assertEqual({job["recipe"] for job in client.jobs()}, {"check-line"})

    def test_a_rule_that_cannot_queue_falls_through_to_the_next(self):
        missing = {"label": "os=linux", "recipe": "missing", "ref": "main", "when": "code"}
        client = self.start([missing, LINUX])
        self.assertEqual(client.claim("spare", ["os=linux"])["recipe"], "check-line")

    def test_workers_claiming_at_once_queue_one_sweep(self):
        client = self.start([LINUX])
        barrier = threading.Barrier(8)

        def claim(index):
            barrier.wait()
            client.claim(f"spare{index}", ["os=linux"])

        threads = [threading.Thread(target=claim, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertEqual(len(client.jobs()), 2)

    def test_an_idle_config_that_is_not_a_list_of_rules_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {"db": str(Path(folder) / "lab.db"), "jobs_dir": str(Path(folder) / "jobs"), "repo": folder,
                      "token": "t"}
            for idle in ({"ref": "main", "recipe_for_label": {"os=linux": "sweep-linux"}},
                         [dict(LINUX, when="weekly")],
                         [{"label": "os=linux", "recipe": "sweep-linux", "when": "code"}]):
                with self.assertRaises(ValueError):
                    server.Lab(dict(config, idle=idle))


class Fanouts(unittest.TestCase):
    def submit_over(self, blocking):
        files = recipe_file(BOOK)
        files["doctrine/blocking.md"] = blocking
        self.repo = Repo(files)
        self.lab = Coordinator(self.repo)
        try:
            with self.assertRaises(urllib.error.HTTPError):
                self.lab.client.submit("sweep-linux", self.repo.head, {}, "sweep")
            return self.lab.client.jobs()
        finally:
            self.lab.close()
            self.repo.close()

    def test_a_fanout_with_no_lines_is_refused(self):
        self.assertEqual(self.submit_over("nothing here" + chr(10)), [])

    def test_a_fanout_with_one_bad_line_queues_nothing(self):
        lines = ["- one :: true", "- it's bad :: true", "- two :: true", ""]
        self.assertEqual(self.submit_over(chr(10).join(lines)), [])


if __name__ == "__main__":
    unittest.main()
