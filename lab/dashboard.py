import html
import time

from . import policy

STYLE = (
    "body{font:15px system-ui,sans-serif;margin:16px;background:#fff;color:#111}"
    "table{border-collapse:collapse;width:100%;margin-bottom:20px}"
    "td,th{border-bottom:1px solid #ddd;padding:6px 4px;text-align:left;vertical-align:top}"
    "h2{font-size:17px;margin:18px 0 6px}.done{color:#11772d}.failed{color:#b3261e}"
    "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}td,th{border-color:#333}}"
)


def _ago(moment):
    return "never" if not moment else f"{int(time.time() - moment)} s ago"


def _table(headers, rows):
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _rank(job):
    return policy.rank(policy.Job(job["id"], job["cls"], frozenset(job["needs"]), job["waiting"], job["short"],
                                  job["overtaken"]))


def render(lab, token):
    escape = html.escape
    store = lab.store
    running = {job["worker"]: job for job in store.jobs(state="running")}
    workers = []
    for worker in store.workers():
        job = running.get(worker["name"])
        verb = "resume" if worker["paused"] else "pause"
        button = (f"<form method='post' action='/api/workers/{escape(worker['name'])}/pause"
                  f"?token={escape(token)}&paused={0 if worker['paused'] else 1}'><button>{verb}</button></form>")
        workers.append([escape(worker["name"]), escape(" ".join(worker["labels"])), _ago(worker["seen"]),
                        f"L-{job['id']} {escape(job['recipe'])} ({escape(job['cls'])})" if job else "", button])
    queue = sorted(store.jobs(state="queued", limit=500), key=lambda job: (-_rank(job), job["id"]))
    queued_rows = [[f"L-{job['id']}", escape(job["cls"]), escape(job["recipe"]), escape(str(job["params"])),
                    job["commit_sha"][:8], "yes" if job["waiting"] else "", str(job["overtaken"])] for job in queue]
    finished = [job for job in store.jobs(limit=60) if job["state"] in ("done", "failed", "cancelled")][:30]
    finished_rows = [[f"L-{job['id']}", escape(job["recipe"]), escape(str(job["params"])),
                      f"<span class='{escape(job['state'])}'>{escape(job['state'])}</span>",
                      escape(str(job["result"].get("metrics", {}))), escape(job["worker"])] for job in finished]
    sweeps = []
    idle = lab.config.get("idle")
    if idle:
        try:
            head = lab.resolve(f"refs/heads/{idle['ref']}")
        except Exception:
            head = ""
        for label in idle["recipe_for_label"]:
            states = {}
            for job in store.jobs(for_ref=f"sweep:{label}:{head}", limit=1000) if head else []:
                states[job["state"]] = states.get(job["state"], 0) + 1
            summary = ", ".join(f"{count} {state}" for state, count in sorted(states.items())) or "not swept"
            sweeps.append([escape(label), head[:8], escape(summary)])
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<meta http-equiv='refresh' content='10'><title>Talus lab</title>"
        f"<style>{STYLE}</style></head><body>"
        "<h2>Machines</h2>" + _table(["machine", "labels", "seen", "running", ""], workers)
        + "<h2>Main swept</h2>" + _table(["platform", "main", "jobs"], sweeps)
        + "<h2>Queue</h2>" + _table(["job", "class", "recipe", "params", "commit", "waited", "overtaken"], queued_rows)
        + "<h2>Recent</h2>" + _table(["job", "recipe", "params", "state", "metrics", "machine"], finished_rows)
        + "</body></html>"
    )
