import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from labfixture import Coordinator, Repo, git, recipe_file
from lab import cli
from lab.worker import Worker

BOOK = {"hello": {"short": True, "params": {"word": "hi"}, "run": "echo {word}"}}


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(recipe_file(BOOK))
        self.lab = Coordinator(self.repo)
        self.home = Path(tempfile.mkdtemp(prefix="labcli-"))
        self.clone = self.home / "clone"
        git("clone", "--quiet", str(self.repo.path), str(self.clone))
        config = self.home / "lab.json"
        config.write_text(json.dumps({"url": self.lab.url, "token": self.lab.token, "remote": str(self.repo.path)}))
        os.environ["LAB_CONFIG"] = str(config)
        self.cwd = os.getcwd()
        os.chdir(self.clone)

    def tearDown(self):
        os.chdir(self.cwd)
        os.environ.pop("LAB_CONFIG", None)
        self.lab.close()
        self.repo.close()
        shutil.rmtree(self.home, ignore_errors=True)

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_submit_pushes_the_commit_and_queues_the_job(self):
        code, out = self.run_cli("submit", "hello", "--param", "word=there", "--class", "gate")
        self.assertEqual(code, 0)
        self.assertTrue(out.strip().startswith("L-"))
        job = self.lab.client.job(int(out.strip()[2:]))
        self.assertEqual(job["params"], {"word": "there"})
        self.assertEqual(job["commit_sha"], git("rev-parse", "HEAD", cwd=self.clone))

    def test_wait_returns_zero_when_every_job_is_done(self):
        code, out = self.run_cli("submit", "hello", "--class", "gate")
        job_id = out.strip()
        workdir = self.home / "worker"
        worker = Worker(self.lab.client, {"name": "spare", "labels": ["os=linux"], "workdir": str(workdir),
                                          "repo_url": str(self.repo.path), "bash": shutil.which("bash"),
                                          "quiet_labels": [], "heartbeat_every": 0.2, "log_every": 0.2})
        thread = threading.Thread(target=worker.run_once)
        thread.start()
        code, out = self.run_cli("wait", job_id)
        thread.join(timeout=30)
        self.assertEqual(code, 0)
        self.assertIn("done", out)
        self.assertTrue(self.lab.client.job(int(job_id[2:]))["waiting"])

    def test_waiting_on_no_jobs_fails(self):
        self.assertEqual(cli.wait_for(self.lab.client, []), 1)

    def test_status_lists_the_queue(self):
        self.run_cli("submit", "hello", "--class", "milestone")
        code, out = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("milestone", out)
        self.assertIn("hello", out)

    def test_cancel_by_id(self):
        _, out = self.run_cli("submit", "hello")
        code, _ = self.run_cli("cancel", out.strip())
        self.assertEqual(code, 0)
        self.assertEqual(self.lab.client.job(int(out.strip()[2:]))["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
