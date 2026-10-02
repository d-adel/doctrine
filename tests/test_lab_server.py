import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from labfixture import Coordinator, Repo, recipe_file

BOOK = {
    "say": {"short": True, "params": {"word": "hi"}, "run": "echo {word}", "metrics": {"answer": "answer ([0-9]+)"}},
    "check-line": {"short": True, "params": {"name": ""}, "run": "echo \"{name}\""},
    "sweep-linux": {"needs": ["os=linux"], "fanout": {"file": "doctrine/blocking.md", "recipe": "check-line",
                                                      "param": "name", "needs": ["os=linux"],
                                                      "pattern": "^- (?P<value>[^\\[\\n]+?) :: "}},
}
BLOCKING = "- one :: true\n- two :: true\n"


class Api(unittest.TestCase):
    def setUp(self):
        files = recipe_file(BOOK)
        files["doctrine/blocking.md"] = BLOCKING
        self.repo = Repo(files)
        self.lab = Coordinator(self.repo, idle={"ref": "main", "recipe_for_label": {"os=linux": "sweep-linux"}})
        self.client = self.lab.client

    def tearDown(self):
        self.lab.close()
        self.repo.close()

    def test_a_request_without_the_token_is_refused(self):
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
        self.assertEqual(first["for_ref"], f"sweep:os=linux:{self.repo.head}")
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
