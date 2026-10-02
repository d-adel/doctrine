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
from unittest import mock

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

    def run_cli(self, *argv, stdin=""):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_lines_submits_one_job_per_value_at_one_commit(self):
        code, out = self.run_cli("lines", "hello", "word", stdin="one\n\n  two  \r\n\n")
        self.assertEqual(code, 0)
        jobs = [self.lab.client.job(int(item[2:])) for item in out.split()]
        self.assertEqual([job["params"] for job in jobs], [{"word": "one"}, {"word": "two"}])
        head = git("rev-parse", "HEAD", cwd=self.clone)
        self.assertEqual({job["commit_sha"] for job in jobs}, {head})
        self.assertEqual({job["cls"] for job in jobs}, {"gate"})
        self.assertEqual(git("--git-dir", str(self.repo.path), "rev-parse", f"refs/lab/{head}"), head)

    def test_lines_takes_the_class_the_commit_and_the_for(self):
        first = git("rev-parse", "HEAD", cwd=self.clone)
        git("-c", "user.email=lab@example.invalid", "-c", "user.name=lab", "commit", "--quiet", "--allow-empty",
            "-m", "later", cwd=self.clone)
        code, out = self.run_cli("lines", "hello", "word", "--class", "experiment", "--commit", "HEAD~1",
                                 "--for", "packet", stdin="one\n")
        self.assertEqual(code, 0)
        job = self.lab.client.job(int(out.strip()[2:]))
        self.assertEqual((job["cls"], job["commit_sha"], job["for_ref"]), ("experiment", first, "packet"))

    def test_lines_with_no_values_fails_and_queues_nothing(self):
        code, out = self.run_cli("lines", "hello", "word", stdin="\n  \n")
        self.assertEqual(code, 1)
        self.assertIn("no values", out)
        self.assertEqual(self.lab.client.jobs(), [])

    def test_lines_with_a_refused_value_leaves_nothing_queued(self):
        code, out = self.run_cli("lines", "hello", "word", stdin="one\nit's\ntwo\n")
        self.assertEqual(code, 1)
        self.assertIn("it's", out)
        self.assertEqual([job["state"] for job in self.lab.client.jobs()], ["cancelled"])

    def test_lines_wait_on_every_job(self):
        with mock.patch.object(cli, "wait_for", return_value=3) as waited:
            code, out = self.run_cli("lines", "hello", "word", "--wait", stdin="one\ntwo\n")
        self.assertEqual(code, 3)
        self.assertEqual(waited.call_args.args[1], [int(item[2:]) for item in out.split()])
        self.assertEqual(len(waited.call_args.args[1]), 2)

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

    def test_submit_carries_needs(self):
        code, out = self.run_cli("submit", "hello", "--class", "gate", "--need", "os=windows")
        self.assertEqual(code, 0)
        self.assertEqual(self.lab.client.job(int(out.strip()[2:]))["needs"], ["os=windows"])

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
