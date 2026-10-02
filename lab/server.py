import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import dashboard, recipes
from .store import Store


class Lab:
    def __init__(self, config):
        self.config = config
        self.store = Store(config["db"])
        self.jobs_dir = Path(config["jobs_dir"])
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.token = config["token"]

    def git(self, *args):
        return subprocess.run(["git", "--git-dir", self.config["repo"], *args],
                              capture_output=True, text=True, check=True).stdout

    def resolve(self, commit):
        return self.git("rev-parse", "--verify", f"{commit}^{{commit}}").strip()

    def book_at(self, sha):
        return recipes.load(self.git("show", f"{sha}:{self.config['recipes_path']}"))

    def submit(self, name, params, commit, cls, for_ref=""):
        sha = self.resolve(commit)
        book = self.book_at(sha)
        if name not in book:
            raise ValueError(f"no recipe {name} at {sha[:8]}")
        recipe = book[name]
        if "fanout" not in recipe:
            recipes.command(recipe, params)
            return [self.store.submit(name, params, sha, recipe.get("needs", []), cls, recipe.get("short", False), for_ref)]
        entries = []
        for child in recipes.fanout(recipe, self.git("show", f"{sha}:{recipe['fanout']['file']}")):
            child_recipe = book[child["recipe"]]
            recipes.command(child_recipe, child["params"])
            entries.append({"recipe": child["recipe"], "params": child["params"], "commit": sha,
                            "needs": sorted(set(child_recipe.get("needs", [])) | set(child["needs"])),
                            "cls": cls, "short": child_recipe.get("short", False), "for_ref": for_ref})
        if not entries:
            raise ValueError(f"recipe {name} fans out to no jobs at {sha[:8]}")
        return self.store.submit_many(entries)

    def idle(self, worker, labels):
        idle = self.config.get("idle")
        if not idle or self.store.paused(worker):
            return False
        for label, sweep in idle["recipe_for_label"].items():
            if label not in labels:
                continue
            try:
                head = self.resolve(f"refs/heads/{idle['ref']}")
                mark = f"sweep:{label}:{head}"
                if self.store.jobs(for_ref=mark, limit=1):
                    continue
                return bool(self.submit(sweep, {}, head, "sweep", mark))
            except (subprocess.CalledProcessError, ValueError, KeyError):
                return False
        return False

    def claim(self, worker, labels):
        self.store.requeue_lost(self.config.get("lost_after", 90))
        job = self.store.claim(worker, labels)
        if job is None and self.idle(worker, labels):
            job = self.store.claim(worker, labels)
        if job is None:
            return None
        job["command"] = recipes.command(self.book_at(job["commit_sha"])[job["recipe"]], job["params"])
        return job

    def log_path(self, job_id):
        return self.jobs_dir / str(job_id) / "log.txt"

    def append_log(self, job_id, data):
        path = self.log_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(data)

    def finish(self, job_id, worker, exit_code, result):
        job = self.store.get(job_id)
        if job is None:
            return False
        path = self.log_path(job_id)
        output = path.read_text(errors="replace") if path.exists() else ""
        recipe = self.book_at(job["commit_sha"]).get(job["recipe"], {})
        return self.store.finish(job_id, worker, exit_code, dict(result, metrics=recipes.metrics(recipe, output)))


def _arg(query, key):
    values = query.get(key)
    return values[0] if values else None


def make_handler(lab):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def _send(self, code, body, kind="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _route(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            token = self.headers.get("X-Lab-Token") or _arg(query, "token")
            parts = [part for part in url.path.split("/") if part]
            return token == lab.token, parts, query

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def do_GET(self):
            allowed, parts, query = self._route()
            if not allowed:
                return self._send(401, {"error": "token"})
            try:
                return self._get(parts, query)
            except (ValueError, KeyError) as error:
                return self._send(400, {"error": str(error)})

        def _get(self, parts, query):
            if not parts:
                return self._send(200, dashboard.render(lab, _arg(query, "token") or "").encode(), "text/html; charset=utf-8")
            if parts == ["api", "jobs"]:
                return self._send(200, lab.store.jobs(state=_arg(query, "state"), recipe=_arg(query, "recipe"),
                                                      commit=_arg(query, "commit"), for_ref=_arg(query, "for_ref")))
            if parts == ["api", "workers"]:
                return self._send(200, lab.store.workers())
            if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                job = lab.store.get(int(parts[2]))
                return self._send(200 if job else 404, job or {"error": "no such job"})
            if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "log":
                path = lab.log_path(int(parts[2]))
                data = path.read_bytes() if path.exists() else b""
                return self._send(200, data[int(_arg(query, "offset") or 0):], "application/octet-stream")
            return self._send(404, {"error": "no such route"})

        def do_POST(self):
            allowed, parts, query = self._route()
            if not allowed:
                return self._send(401, {"error": "token"})
            raw = self._body()
            try:
                if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "log":
                    lab.append_log(int(parts[2]), raw)
                    return self._send(200, {"ok": True})
                if len(parts) == 4 and parts[:2] == ["api", "workers"] and parts[3] == "pause":
                    lab.store.set_paused(parts[2], _arg(query, "paused") == "1")
                    self.send_response(303)
                    self.send_header("Location", f"/?token={lab.token}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                body = json.loads(raw) if raw else {}
                if parts == ["api", "jobs"]:
                    ids = lab.submit(body["recipe"], body.get("params", {}), body["commit"],
                                     body.get("cls", "experiment"), body.get("for", ""))
                    return self._send(200, {"ids": ids})
                if parts == ["api", "wait"]:
                    lab.store.mark_waiting([int(job_id) for job_id in body["ids"]])
                    return self._send(200, {"ok": True})
                if parts == ["api", "claim"]:
                    return self._send(200, {"job": lab.claim(body["worker"], body.get("labels", []))})
                if len(parts) == 4 and parts[:2] == ["api", "jobs"]:
                    job_id = int(parts[2])
                    if parts[3] == "heartbeat":
                        return self._send(200, {"ok": lab.store.heartbeat(job_id, body["worker"])})
                    if parts[3] == "finish":
                        return self._send(200, {"ok": lab.finish(job_id, body["worker"], int(body["exit_code"]),
                                                                 body.get("result", {}))})
                    if parts[3] == "cancel":
                        return self._send(200, {"ok": lab.store.cancel(job_id)})
                return self._send(404, {"error": "no such route"})
            except (ValueError, KeyError, subprocess.CalledProcessError) as error:
                return self._send(400, {"error": str(error)})

    return Handler


def reap(lab, every):
    while True:
        time.sleep(every)
        lab.store.requeue_lost(lab.config.get("lost_after", 90))


def serve(config):
    lab = Lab(config)
    httpd = ThreadingHTTPServer((config.get("bind", "0.0.0.0"), int(config.get("port", 8765))), make_handler(lab))
    httpd.lab = lab
    every = max(config.get("lost_after", 90) / 3, 0.1)
    threading.Thread(target=reap, args=(lab, every), daemon=True).start()
    return httpd
