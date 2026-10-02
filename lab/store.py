import json
import sqlite3
import threading
import time

from . import policy

FINISHED = ("done", "failed", "cancelled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe TEXT NOT NULL,
    params TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    needs TEXT NOT NULL,
    cls TEXT NOT NULL,
    short INTEGER NOT NULL,
    for_ref TEXT NOT NULL DEFAULT '',
    waiting INTEGER NOT NULL DEFAULT 0,
    overtaken INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'queued',
    worker TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    submitted REAL NOT NULL,
    started REAL,
    finished REAL,
    heartbeat REAL,
    exit_code INTEGER,
    result TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS workers (
    name TEXT PRIMARY KEY,
    labels TEXT NOT NULL,
    seen REAL NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0
);
"""


def _job(row):
    if row is None:
        return None
    job = dict(row)
    job["params"] = json.loads(job["params"])
    job["needs"] = json.loads(job["needs"])
    job["result"] = json.loads(job["result"])
    job["short"] = bool(job["short"])
    job["waiting"] = bool(job["waiting"])
    return job


def _moment(now):
    return time.time() if now is None else now


class Store:
    def __init__(self, path):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def submit(self, recipe, params, commit, needs, cls, short, for_ref="", now=None):
        if cls not in policy.CLASSES:
            raise ValueError(f"unknown class {cls}")
        with self._lock:
            cursor = self._db.execute(
                "INSERT INTO jobs (recipe, params, commit_sha, needs, cls, short, for_ref, submitted)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (recipe, json.dumps(params, sort_keys=True), commit, json.dumps(sorted(needs)), cls,
                 int(bool(short)), for_ref, _moment(now)),
            )
            self._db.commit()
            return cursor.lastrowid

    def get(self, job_id):
        with self._lock:
            return _job(self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def jobs(self, state=None, recipe=None, commit=None, for_ref=None, limit=200):
        clauses, values = [], []
        for column, value in (("state", state), ("recipe", recipe), ("commit_sha", commit), ("for_ref", for_ref)):
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._db.execute(f"SELECT * FROM jobs{where} ORDER BY id DESC LIMIT ?", (*values, limit)).fetchall()
        return [_job(row) for row in rows]

    def claim(self, worker, labels, now=None):
        moment = _moment(now)
        with self._lock:
            self._touch(worker, labels, moment)
            if self._is_paused(worker):
                self._db.commit()
                return None
            rows = self._db.execute("SELECT * FROM jobs WHERE state = 'queued' ORDER BY id").fetchall()
            queue = [
                policy.Job(row["id"], row["cls"], frozenset(json.loads(row["needs"])), bool(row["waiting"]),
                           bool(row["short"]), row["overtaken"])
                for row in rows
            ]
            chosen = policy.pick(queue, labels)
            if chosen is None:
                self._db.commit()
                return None
            self._db.executemany(
                "UPDATE jobs SET overtaken = overtaken + 1 WHERE id = ?",
                [(job_id,) for job_id in policy.passed_over(queue, labels, chosen)],
            )
            self._db.execute(
                "UPDATE jobs SET state = 'running', worker = ?, started = ?, heartbeat = ?, attempts = attempts + 1"
                " WHERE id = ?",
                (worker, moment, moment, chosen.id),
            )
            self._db.commit()
            return _job(self._db.execute("SELECT * FROM jobs WHERE id = ?", (chosen.id,)).fetchone())

    def heartbeat(self, job_id, worker, now=None):
        with self._lock:
            cursor = self._db.execute(
                "UPDATE jobs SET heartbeat = ? WHERE id = ? AND worker = ? AND state = 'running'",
                (_moment(now), job_id, worker),
            )
            self._db.commit()
            return cursor.rowcount == 1

    def finish(self, job_id, worker, exit_code, result, now=None):
        state = "done" if exit_code == 0 else "failed"
        with self._lock:
            cursor = self._db.execute(
                "UPDATE jobs SET state = ?, exit_code = ?, result = ?, finished = ?"
                " WHERE id = ? AND worker = ? AND state = 'running'",
                (state, exit_code, json.dumps(result, sort_keys=True), _moment(now), job_id, worker),
            )
            self._db.commit()
            return cursor.rowcount == 1

    def cancel(self, job_id, now=None):
        with self._lock:
            cursor = self._db.execute(
                "UPDATE jobs SET state = 'cancelled', finished = ? WHERE id = ? AND state IN ('queued', 'running')",
                (_moment(now), job_id),
            )
            self._db.commit()
            return cursor.rowcount == 1

    def mark_waiting(self, job_ids):
        with self._lock:
            self._db.executemany("UPDATE jobs SET waiting = 1 WHERE id = ?", [(job_id,) for job_id in job_ids])
            self._db.commit()

    def requeue_lost(self, timeout, now=None, max_attempts=2):
        moment = _moment(now)
        changed = []
        with self._lock:
            rows = self._db.execute(
                "SELECT id, attempts FROM jobs WHERE state = 'running' AND heartbeat < ?", (moment - timeout,)
            ).fetchall()
            for row in rows:
                if row["attempts"] >= max_attempts:
                    self._db.execute(
                        "UPDATE jobs SET state = 'failed', finished = ?, result = ? WHERE id = ?",
                        (moment, json.dumps({"reason": "lost"}), row["id"]),
                    )
                else:
                    self._db.execute("UPDATE jobs SET state = 'queued', worker = '' WHERE id = ?", (row["id"],))
                changed.append(row["id"])
            self._db.commit()
        return changed

    def _touch(self, name, labels, moment):
        self._db.execute(
            "INSERT INTO workers (name, labels, seen) VALUES (?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET labels = excluded.labels, seen = excluded.seen",
            (name, json.dumps(sorted(labels)), moment),
        )

    def touch_worker(self, name, labels, now=None):
        with self._lock:
            self._touch(name, labels, _moment(now))
            self._db.commit()

    def _is_paused(self, name):
        row = self._db.execute("SELECT paused FROM workers WHERE name = ?", (name,)).fetchone()
        return bool(row and row["paused"])

    def paused(self, name):
        with self._lock:
            return self._is_paused(name)

    def set_paused(self, name, paused):
        with self._lock:
            self._db.execute(
                "INSERT INTO workers (name, labels, seen, paused) VALUES (?, '[]', 0, ?)"
                " ON CONFLICT(name) DO UPDATE SET paused = excluded.paused",
                (name, int(bool(paused))),
            )
            self._db.commit()

    def workers(self):
        with self._lock:
            rows = self._db.execute("SELECT * FROM workers ORDER BY name").fetchall()
        return [dict(row, labels=json.loads(row["labels"]), paused=bool(row["paused"])) for row in rows]
