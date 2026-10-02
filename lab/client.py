import json
import urllib.parse
import urllib.request


class Client:
    def __init__(self, url, token, timeout=30):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def call(self, method, path, body=None, raw=None):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        kind = "application/octet-stream" if raw is not None else "application/json"
        request = urllib.request.Request(self.url + path, data=data, method=method,
                                         headers={"X-Lab-Token": self.token, "Content-Type": kind})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = response.read()
            if response.headers.get_content_type() == "application/json":
                return json.loads(payload) if payload else None
            return payload

    def submit(self, recipe, commit, params=None, cls="experiment", for_ref=""):
        body = {"recipe": recipe, "commit": commit, "params": params or {}, "cls": cls, "for": for_ref}
        return self.call("POST", "/api/jobs", body)["ids"]

    def job(self, job_id):
        return self.call("GET", f"/api/jobs/{job_id}")

    def jobs(self, **filters):
        query = urllib.parse.urlencode({key: value for key, value in filters.items() if value is not None})
        return self.call("GET", "/api/jobs" + (f"?{query}" if query else ""))

    def log(self, job_id, offset=0):
        return self.call("GET", f"/api/jobs/{job_id}/log?offset={offset}")

    def wait_mark(self, ids):
        self.call("POST", "/api/wait", {"ids": list(ids)})

    def claim(self, worker, labels):
        return self.call("POST", "/api/claim", {"worker": worker, "labels": sorted(labels)})["job"]

    def heartbeat(self, job_id, worker):
        return self.call("POST", f"/api/jobs/{job_id}/heartbeat", {"worker": worker})["ok"]

    def append_log(self, job_id, data):
        self.call("POST", f"/api/jobs/{job_id}/log", raw=data)

    def finish(self, job_id, worker, exit_code, result):
        body = {"worker": worker, "exit_code": exit_code, "result": result}
        return self.call("POST", f"/api/jobs/{job_id}/finish", body)["ok"]

    def cancel(self, job_id):
        return self.call("POST", f"/api/jobs/{job_id}/cancel", {})["ok"]

    def pause(self, name, paused):
        self.call("POST", f"/api/workers/{urllib.parse.quote(name)}/pause?paused={int(bool(paused))}", {})

    def workers(self):
        return self.call("GET", "/api/workers")
