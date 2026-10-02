import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab import server
from lab.client import Client


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class Repo:
    def __init__(self, files):
        self.root = Path(tempfile.mkdtemp(prefix="labrepo-"))
        self.path = self.root / "repo.git"
        self.work = self.root / "work"
        git("init", "--quiet", "--bare", str(self.path))
        git("--git-dir", str(self.path), "config", "uploadpack.allowReachableSHA1InWant", "true")
        git("init", "--quiet", "-b", "main", str(self.work))
        git("config", "user.email", "lab@example.invalid", cwd=self.work)
        git("config", "user.name", "lab", cwd=self.work)
        self.head = self.commit(files)

    def commit(self, files):
        for name, text in files.items():
            target = self.work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, newline="\n")
        git("add", "-A", cwd=self.work)
        git("commit", "--quiet", "-m", "fixture", cwd=self.work)
        git("push", "--quiet", str(self.path), "main:main", cwd=self.work)
        self.head = git("rev-parse", "HEAD", cwd=self.work)
        return self.head

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Coordinator:
    def __init__(self, repo, **extra):
        self.dir = Path(tempfile.mkdtemp(prefix="labd-"))
        self.token = "fixture-token"
        config = {"db": str(self.dir / "lab.db"), "jobs_dir": str(self.dir / "jobs"), "repo": str(repo.path),
                  "token": self.token, "recipes_path": "doctrine/lab/recipes.json", "lost_after": 90}
        config.update(extra)
        self.httpd = server.serve(dict(config, bind="127.0.0.1", port=0))
        self.lab = self.httpd.lab
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client(self.url, self.token)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)


def recipe_file(book):
    return {"doctrine/lab/recipes.json": json.dumps({"recipes": book})}
