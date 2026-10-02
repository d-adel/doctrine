import os
import platform
import subprocess
import threading
import time
from pathlib import Path

from . import host


class Worker:
    def __init__(self, client, config):
        self.client = client
        self.name = config["name"]
        self.labels = set(config["labels"])
        self.workdir = Path(config["workdir"])
        self.tree = self.workdir / "tree"
        self.logs = self.workdir / "logs"
        self.repo_url = config["repo_url"]
        self.bash = config.get("bash", "bash")
        self.env_file = config.get("env_file", "")
        self.owner = config.get("owner", False)
        self.idle_after = config.get("idle_after", 600)
        self.quiet_labels = set(config.get("quiet_labels", ["quiet", "reference"]))
        self.quiet_cpu = config.get("quiet_cpu", 15)
        self.quiet_gpu = config.get("quiet_gpu", 10)
        self.heartbeat_every = config.get("heartbeat_every", 15)
        self.log_every = config.get("log_every", 3)
        self.poll = config.get("poll", 10)

    def owner_present(self):
        return bool(self.owner) and host.owner_present(self.idle_after)

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
            subprocess.run(["git", "clone", "--quiet", "--no-checkout", self.repo_url, str(self.tree)], check=True)
        subprocess.run(["git", "-C", str(self.tree), "fetch", "--quiet", "origin", sha], check=True)
        subprocess.run(["git", "-C", str(self.tree), "checkout", "--quiet", "--force", sha], check=True)
        subprocess.run(["git", "-C", str(self.tree), "clean", "-ffdxq", "-e", "build-dev", "-e", "build-release"],
                       check=True)

    def machine(self):
        return {"name": self.name, "platform": platform.platform(), "gpu": host.gpu_name()}

    def run_once(self):
        if self.owner_present():
            return False
        job = self.client.claim(self.name, self.labels_now())
        if not job:
            return False
        self.execute(job)
        return True

    def execute(self, job):
        job_id = job["id"]
        logdir = self.logs / str(job_id)
        logdir.mkdir(parents=True, exist_ok=True)
        load = {"cpu": host.cpu_load(0.5), "gpu": host.gpu_load()}
        began = time.time()
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

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        cancelled = False
        last_beat = last_send = 0.0
        while process.poll() is None:
            now = time.time()
            if now - last_send >= self.log_every:
                self.send(job_id, pending, guard)
                last_send = now
            if now - last_beat >= self.heartbeat_every:
                last_beat = now
                if not self.client.heartbeat(job_id, self.name):
                    host.kill(process)
                    cancelled = True
                    break
            if self.owner_present():
                host.suspend(process)
                while self.owner_present():
                    self.client.heartbeat(job_id, self.name)
                    time.sleep(self.poll)
                host.resume(process)
            time.sleep(0.05)
        process.wait()
        reader.join(timeout=10)
        process.stdout.close()
        self.send(job_id, pending, guard)
        if cancelled:
            return
        result = {"machine": self.machine(), "load": load, "seconds": round(time.time() - began, 3)}
        self.client.finish(job_id, self.name, process.returncode, result)

    def send(self, job_id, pending, guard):
        with guard:
            data = bytes(pending)
            pending.clear()
        if data:
            self.client.append_log(job_id, data)

    def serve_forever(self):
        while True:
            try:
                if self.run_once():
                    continue
            except OSError as error:
                print(f"lab worker {self.name}: {error}", flush=True)
            time.sleep(self.poll)
