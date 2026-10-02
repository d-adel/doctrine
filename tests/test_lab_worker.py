import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from labfixture import Coordinator, Repo, recipe_file
from lab.worker import Worker

BOOK = {
    "hello": {"short": True, "run": "echo hello $LAB_JOB; echo answer 42; cat marker.txt",
              "metrics": {"answer": "answer ([0-9]+)"}},
    "fail": {"run": "echo broken; exit 3"},
    "slow": {"run": "for i in $(seq 1 200); do echo tick $i; sleep 0.1; done"},
    "windows-only": {"needs": ["os=windows"], "run": "echo windows"},
}


def worker_for(coordinator, repo, name, labels, **extra):
    workdir = Path(tempfile.mkdtemp(prefix=f"labw-{name}-"))
    config = {"name": name, "labels": labels, "workdir": str(workdir), "repo_url": str(repo.path),
              "bash": shutil.which("bash"), "heartbeat_every": 0.2, "log_every": 0.2, "poll": 0.2,
              "quiet_labels": []}
    config.update(extra)
    return Worker(coordinator.client, config), workdir


class Runs(unittest.TestCase):
    def setUp(self):
        files = recipe_file(BOOK)
        files["marker.txt"] = "first commit\n"
        self.repo = Repo(files)
        self.lab = Coordinator(self.repo, lost_after=1)
        self.client = self.lab.client
        self.dirs = []

    def tearDown(self):
        self.lab.close()
        self.repo.close()
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def worker(self, name, labels, **extra):
        worker, path = worker_for(self.lab, self.repo, name, labels, **extra)
        self.dirs.append(path)
        return worker

    def test_a_job_runs_at_its_commit_and_reports_its_metrics(self):
        first = self.repo.head
        self.repo.commit({"marker.txt": "second commit\n"})
        [job_id] = self.client.submit("hello", first, {}, "gate")
        self.assertTrue(self.worker("spare", ["os=linux"]).run_once())
        job = self.client.job(job_id)
        self.assertEqual(job["state"], "done")
        self.assertEqual(job["result"]["metrics"], {"answer": 42.0})
        log = self.client.log(job_id).decode()
        self.assertIn(f"hello {job_id}", log)
        self.assertIn("first commit", log)

    def test_a_failing_command_fails_the_job_with_its_exit_code(self):
        [job_id] = self.client.submit("fail", self.repo.head, {}, "gate")
        self.worker("spare", ["os=linux"]).run_once()
        job = self.client.job(job_id)
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["exit_code"], 3)

    def test_a_job_goes_only_to_a_worker_with_its_labels(self):
        [job_id] = self.client.submit("windows-only", self.repo.head, {}, "gate")
        self.assertFalse(self.worker("spare", ["os=linux"]).run_once())
        self.assertTrue(self.worker("desktop", ["os=windows"]).run_once())
        self.assertEqual(self.client.job(job_id)["worker"], "desktop")

    def test_cancel_kills_the_running_command(self):
        [job_id] = self.client.submit("slow", self.repo.head, {}, "gate")
        worker = self.worker("spare", ["os=linux"])
        thread = threading.Thread(target=worker.run_once)
        thread.start()
        while self.client.job(job_id)["state"] != "running":
            time.sleep(0.05)
        time.sleep(0.5)
        self.client.cancel(job_id)
        thread.join(timeout=15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.client.job(job_id)["state"], "cancelled")
        self.assertNotIn("tick 200", self.client.log(job_id).decode())

    def test_a_silent_worker_loses_its_job_to_another(self):
        [job_id] = self.client.submit("hello", self.repo.head, {}, "gate")
        self.assertEqual(self.client.claim("ghost", ["os=linux"])["id"], job_id)
        time.sleep(1.5)
        self.assertTrue(self.worker("spare", ["os=linux"]).run_once())
        job = self.client.job(job_id)
        self.assertEqual(job["state"], "done")
        self.assertEqual(job["worker"], "spare")
        self.assertEqual(job["attempts"], 2)

    def test_quiet_labels_drop_under_load(self):
        worker = self.worker("desktop", ["os=windows", "reference"], quiet_labels=["reference"], quiet_cpu=-1)
        self.assertEqual(worker.labels_now(), {"os=windows"})


if __name__ == "__main__":
    unittest.main()
