import html
import time

from . import policy

STYLE = (
    "body{font:15px system-ui,sans-serif;margin:16px;background:#fff;color:#111}"
    "table{border-collapse:collapse;width:100%;margin-bottom:20px}"
    "td,th{border-bottom:1px solid #ddd;padding:6px 4px;text-align:left;vertical-align:top}"
    "h2{font-size:17px;margin:18px 0 6px}.done{color:#11772d}.failed{color:#b3261e}"
    ".plan{background:#b3261e;color:#fff;padding:10px;font-weight:600;margin-bottom:12px}"
    ".score{font-size:44px;font-weight:700;line-height:1.1}"
    "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}td,th{border-color:#333}}"
)
SEEN = 120
RUNS = 20


def _ago(moment):
    return "never" if not moment else f"{int(time.time() - moment)} s ago"


def _when(moment):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(moment)) if moment else ""


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _number(value):
    if value is None:
        return ""
    return f"{value:g}" if _numeric(value) else str(value)


def _change(value, previous):
    return f"{round(value - previous, 6):+g}" if _numeric(value) and _numeric(previous) else ""


def scoreboard(lab):
    board = lab.config.get("scoreboard")
    if not board:
        return ""
    escape = html.escape
    metric, more, target = board["metric"], board.get("more", []), board["target"]
    runs = lab.store.done(board["recipe"], RUNS)
    values = [run["result"].get("metrics", {}).get(metric) for run in runs] + [None]
    rows = []
    for index, run in enumerate(runs):
        metrics = run["result"].get("metrics", {})
        rows.append([escape(run["commit_sha"][:8]), escape(_when(run["finished"])), escape(_number(values[index]))]
                    + [escape(_number(metrics.get(name))) for name in more]
                    + [escape(_change(values[index], values[index + 1])), escape(_number(target))])
    if not runs:
        headline = "<p>no runs yet</p>"
    elif _numeric(values[0]) and _numeric(target) and target:
        headline = (f"<div class='score'>{escape(_number(values[0]))}</div>"
                    f"<p>{values[0] / target:.2f}&times; the target of {escape(_number(target))}</p>")
    else:
        headline = f"<div class='score'>{escape(_number(values[0]))}</div>"
    return (f"<h2>Scoreboard: {escape(board['recipe'])} {escape(metric)}</h2>" + headline
            + _table(["commit", "finished", metric, *more, "change", "target"], rows))


def plan_banner(store, running, now):
    machines = []
    for worker in store.workers():
        job = running.get(worker["name"])
        seen = max(worker["seen"], job["heartbeat"] or 0) if job else worker["seen"]
        if now - seen > SEEN:
            continue
        if job and job["cls"] != "sweep":
            return ""
        machines.append(worker["name"])
    if not machines:
        return ""
    return f"<div class='plan'>Plan empty: {html.escape(', '.join(machines))}</div>"


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
    rules = []
    for rule in lab.config.get("idle", []):
        name = lab.rule_name(rule)
        mark = store.idle_mark(name)
        head = mark["head"] if mark else ""
        states = {}
        for job in store.jobs(for_ref=f"idle:{name}:{head}", limit=1000) if head else []:
            states[job["state"]] = states.get(job["state"], 0) + 1
        summary = ", ".join(f"{count} {state}" for state, count in sorted(states.items()))
        rules.append([escape(rule["label"]), escape(rule["recipe"]), escape(rule["ref"]), escape(rule["when"]),
                      escape(head[:8]), _ago(mark["ran"]) if mark else "never",
                      escape(summary or ("records only" if mark else "never ran"))])
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        "<meta http-equiv='refresh' content='10'><title>Talus lab</title>"
        f"<style>{STYLE}</style></head><body>"
        + plan_banner(store, running, time.time()) + scoreboard(lab)
        + "<h2>Machines</h2>" + _table(["machine", "labels", "seen", "running", ""], workers)
        + "<h2>Idle rules</h2>" + _table(["label", "recipe", "ref", "when", "head", "ran", "jobs"], rules)
        + "<h2>Queue</h2>" + _table(["job", "class", "recipe", "params", "commit", "waited", "overtaken"], queued_rows)
        + "<h2>Recent</h2>" + _table(["job", "recipe", "params", "state", "metrics", "machine"], finished_rows)
        + "</body></html>"
    )
