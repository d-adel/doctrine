import contextlib
import http.client
import os
import platform
import subprocess
import threading
import time
from pathlib import Path

from . import host

TRANSIENT = (OSError, ValueError, http.client.HTTPException)


class Worker:
    def __init__(self, client, config):
        self.client = client
        self.name = config["name"]
        self.labels = set(config["labels"]) | {f"name={self.name}"}
        self.workdir = Path(config["workdir"])
        self.tree = self.workdir / "tree"
        self.logs = self.workdir / "logs"
        self.repo_url = config["repo_url"]
        self.bash = config.get("bash", "bash")
        self.env_file = config.get("env_file", "")
        self.owner = config.get("owner", False)
        self.presence = host.Presence(config.get("presence_minutes", 3), config.get("presence_window", 300),
                                      cursor=host.cursor_position if config.get("presence_cursor") else None,
                                      travel=config.get("presence_cursor_pixels", 16))
        self.quiet_labels = set(config.get("quiet_labels", ["quiet", "reference"]))
        self.quiet_cpu = config.get("quiet_cpu", 15)
        self.quiet_gpu = config.get("quiet_gpu", 10)
        self.heartbeat_every = config.get("heartbeat_every", 15)
        self.log_every = config.get("log_every", 3)
        self.poll = config.get("poll", 10)
        self.lost_after = config.get("lost_after", 90)
        self.drain_wait = config.get("drain_wait", 10)

    def owner_present(self):
        return bool(self.owner) and self.presence.present()

    def labels_now(self):
        labels = set(self.labels)
        if labels & self.quiet_labels:
            gpu = host.gpu_load()
            if host.cpu_load(0.5) > self.quiet_cpu or (gpu is not None and gpu > self.quiet_gpu):
                labels -= self.quiet_labels
        return labels

    def checkout(self, sha):
        if not (self.tree / ".git").exists():
            self.workdir.mkdir(parents=True, exist_ok=True)
            host.hidden_run(["git", "clone", "--quiet", "--no-checkout", self.repo_url, str(self.tree)], check=True)
        host.hidden_run(["git", "-C", str(self.tree), "fetch", "--quiet", "origin", sha], check=True)
        host.hidden_run(["git", "-C", str(self.tree), "checkout", "--quiet", "--force", sha], check=True)
        host.hidden_run(["git", "-C", str(self.tree), "clean", "-ffdxq", "-e", "build-dev", "-e", "build-release"],
                       check=True)

    def machine(self):
        return {"name": self.name, "platform": platform.platform(), "gpu": host.gpu_name()}

    def run_once(self):
        if self.owner_present():
            self.client.claim(self.name, self.labels, held=True)
            return False
        job = self.client.claim(self.name, self.labels_now())
        if not job:
            return False
        self.execute(job)
        return True

    def execute(self, job):
        with self.beating(job["id"]) as status:
            self.supervise(job, status)

    def supervise(self, job, status):
        job_id = job["id"]
        logdir = self.logs / str(job_id)
        logdir.mkdir(parents=True, exist_ok=True)
        began = time.time()
        load = {"cpu": host.cpu_load(0.5), "gpu": host.gpu_load()}
        try:
            self.checkout(job["commit_sha"])
        except subprocess.CalledProcessError as error:
            self.client.append_log(job_id, f"lab: checkout failed: {error}\n".encode())
            self.client.finish(job_id, self.name, 125, {"reason": "checkout", "machine": self.machine()})
            return
        prefix = f". '{self.env_file}'; " if self.env_file else ""
        env = dict(os.environ, LAB_JOB=str(job_id), LAB_COMMIT=job["commit_sha"], LAB_LOGDIR=logdir.as_posix())
        process = host.start([self.bash, "-c", f"set -o pipefail; {prefix}{job['command']}"], str(self.tree), env)
        pending = bytearray()
        guard = threading.Lock()

        def drain():
            with (logdir / "log.txt").open("ab") as local:
                for chunk in iter(lambda: process.stdout.read1(65536), b""):
                    local.write(chunk)
                    with guard:
                        pending.extend(chunk)

        def lost():
            return status["cancelled"] or time.time() - status["heard"] > self.lost_after

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        cancelled = False
        last_send = 0.0
        try:
            while process.poll() is None:
                now = time.time()
                if now - last_send >= self.log_every:
                    self.send(job_id, pending, guard)
                    last_send = now
                if lost():
                    cancelled = True
                    break
                if self.owner_present():
                    host.suspend(process)
                    while self.owner_present() and not lost():
                        time.sleep(self.poll)
                    if lost():
                        cancelled = True
                        break
                    host.resume(process)
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                host.kill(process)
            process.wait()
            reader.join(timeout=self.drain_wait)
            if not reader.is_alive():
                process.stdout.close()
        self.send(job_id, pending, guard)
        if cancelled:
            return
        result = {"machine": self.machine(), "load": load, "seconds": round(time.time() - began, 3)}
        deadline = time.time() + self.lost_after
        while True:
            try:
                self.client.finish(job_id, self.name, process.returncode, result)
                return
            except TRANSIENT:
                if time.time() > deadline:
                    raise
                time.sleep(self.heartbeat_every)

    def send(self, job_id, pending, guard):
        with guard:
            data = bytes(pending)
            pending.clear()
        if not data:
            return
        try:
            self.client.append_log(job_id, data)
        except TRANSIENT:
            with guard:
                pending[0:0] = data

    @contextlib.contextmanager
    def beating(self, job_id):
        status = {"cancelled": False, "heard": time.time()}
        stop = threading.Event()

        def loop():
            while not stop.wait(self.heartbeat_every):
                alive = self.beat(job_id)
                if alive:
                    status["heard"] = time.time()
                elif alive is False:
                    status["cancelled"] = True

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        try:
            yield status
        finally:
            stop.set()
            thread.join()

    def beat(self, job_id):
        try:
            return bool(self.client.heartbeat(job_id, self.name))
        except TRANSIENT:
            return None

    def serve_forever(self):
        while True:
            try:
                if self.run_once():
                    continue
            except Exception as error:
                print(f"lab worker {self.name}: {error!r}", flush=True)
            time.sleep(self.poll)
