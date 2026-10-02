import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

from .client import Client
from .store import FINISHED


def load_config(path):
    config = json.loads(Path(path).read_text())
    if "token" not in config and "token_file" in config:
        config["token"] = Path(config["token_file"]).read_text().strip()
    return config


def client_config():
    return load_config(os.environ.get("LAB_CONFIG") or Path.home() / ".lab.json")


def job_id(text):
    return int(text[2:] if text.upper().startswith("L-") else text)


def describe(job):
    metrics = json.dumps(job["result"].get("metrics", {}))
    return (f"L-{job['id']} {job['cls']} {job['recipe']} {json.dumps(job['params'])} {job['commit_sha'][:8]} "
            f"{job['state']} exit {job['exit_code']} {job['worker']} {metrics}")


def wait_for(client, ids, poll=5):
    if not ids:
        print("no jobs to wait for", flush=True)
        return 1
    client.wait_mark(ids)
    while True:
        jobs = [client.job(item) for item in ids]
        if all(job["state"] in FINISHED for job in jobs):
            break
        time.sleep(poll)
    for job in jobs:
        print(describe(job))
    return 0 if all(job["state"] == "done" for job in jobs) else 1


def push_commit(config, commit):
    sha = subprocess.run(["git", "rev-parse", "--verify", f"{commit}^{{commit}}"],
                         capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "push", "--quiet", config["remote"], f"{sha}:refs/lab/{sha}"], check=True)
    return sha


def submit_lines(client, config, args):
    values = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
    if not values:
        print("lab lines: no values on stdin", flush=True)
        return 1
    sha = push_commit(config, args.commit)
    ids = []
    for value in values:
        try:
            ids += client.submit(args.recipe, sha, {args.param: value}, args.cls, args.for_ref, args.needs)
        except urllib.error.HTTPError as error:
            for item in ids:
                client.cancel(item)
            reason = error.read().decode(errors="replace")
            print(f"lab lines: {value} refused, nothing left queued: {reason}", flush=True)
            return 1
    print(" ".join(f"L-{item}" for item in ids), flush=True)
    return wait_for(client, ids) if args.wait else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lab")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("serve", "worker"):
        commands.add_parser(name).add_argument("--config", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("recipe")
    submit.add_argument("--param", action="append", default=[])
    lines = commands.add_parser("lines")
    lines.add_argument("recipe")
    lines.add_argument("param")
    for command, cls in ((submit, "experiment"), (lines, "gate")):
        command.add_argument("--commit", default="HEAD")
        command.add_argument("--class", dest="cls", default=cls)
        command.add_argument("--for", dest="for_ref", default="")
        command.add_argument("--need", dest="needs", action="append", default=[])
        command.add_argument("--wait", action="store_true")
    commands.add_parser("push").add_argument("ref")
    commands.add_parser("status")
    commands.add_parser("wait").add_argument("ids", nargs="+")
    logs = commands.add_parser("logs")
    logs.add_argument("id")
    logs.add_argument("-f", dest="follow", action="store_true")
    commands.add_parser("cancel").add_argument("ids", nargs="+")
    commands.add_parser("pause").add_argument("name")
    commands.add_parser("resume").add_argument("name")
    args = parser.parse_args(argv)

    if args.command == "serve":
        from . import server
        httpd = server.serve(load_config(args.config))
        print(f"lab coordinator on {httpd.server_address[0]}:{httpd.server_address[1]}", flush=True)
        httpd.serve_forever()
        return 0
    if args.command == "worker":
        from .worker import Worker
        config = load_config(args.config)
        Worker(Client(config["url"], config["token"]), config).serve_forever()
        return 0

    config = client_config()
    client = Client(config["url"], config["token"])
    if args.command == "submit":
        sha = push_commit(config, args.commit)
        params = dict(item.split("=", 1) for item in args.param)
        ids = client.submit(args.recipe, sha, params, args.cls, args.for_ref, args.needs)
        print(" ".join(f"L-{item}" for item in ids), flush=True)
        return wait_for(client, ids) if args.wait else 0
    if args.command == "lines":
        return submit_lines(client, config, args)
    if args.command == "push":
        subprocess.run(["git", "push", "--quiet", config["remote"], f"{args.ref}:refs/heads/{args.ref}"], check=True)
        return 0
    if args.command == "status":
        for worker in client.workers():
            state = "paused" if worker["paused"] else f"seen {int(time.time() - worker['seen'])} s ago"
            print(f"{worker['name']} [{' '.join(worker['labels'])}] {state}")
        for job in client.jobs(state="running") + client.jobs(state="queued"):
            print(describe(job))
        return 0
    if args.command == "wait":
        return wait_for(client, [job_id(item) for item in args.ids])
    if args.command == "logs":
        offset = 0
        while True:
            data = client.log(job_id(args.id), offset)
            sys.stdout.write(data.decode(errors="replace"))
            sys.stdout.flush()
            offset += len(data)
            if not args.follow:
                return 0
            if client.job(job_id(args.id))["state"] in FINISHED:
                rest = client.log(job_id(args.id), offset)
                sys.stdout.write(rest.decode(errors="replace"))
                sys.stdout.flush()
                return 0
            time.sleep(2)
    if args.command == "cancel":
        return 0 if all(client.cancel(job_id(item)) for item in args.ids) else 1
    if args.command in ("pause", "resume"):
        client.pause(args.name, args.command == "pause")
        return 0
    return 2
