import argparse
import datetime
import fnmatch
import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

TAG_KEYS = {
    "kind",
    "state",
    "lineage",
    "severity",
    "rests-on",
    "stale",
    "regime",
    "bound-in",
    "validated-in",
    "covers",
    "regime-map",
    "judged-by",
    "confidence",
    "outcome",
    "changed",
}
DEFAULT_KINDS = {"C": "defect", "E": "result", "D": "decision", "A": "audit", "O": "reference"}
DONE_STATES = {"done", "closed", "resolved", "repaired", "superseded", "falsified"}
ROW_ID = re.compile(r"^\|\s*([A-Z]{1,3}-\d+)\s*\|")
ANY_ID = re.compile(r"\b([A-Z]{1,3}-\d+)\b")
LINEAGE_KEY = re.compile(r"^(layer|regime|invariant|criterion|decision):[\w./+-]+$")
REOPEN = re.compile(r"\bReopen (?:if|when|with|on|above|at)\b(?:[^|;.]|\.(?=\d))*")
OBSERVES = re.compile(r"\bObserves: ((?:[^|;.]|\.(?=\d))*)")
CITED_SECTIONS = ("Moves", "Serves", "Accepted Design", "Repairs", "Criteria", "Checks")
ORACLE_KIND = re.compile(r"(^|\s)(spec|exact:|analytic:|invariant:|reference:|relative|regression)")


class Findings:
    def __init__(self):
        self.items = []

    def block(self, code, message):
        self.items.append(("BLOCK", code, message))

    def warn(self, code, message):
        self.items.append(("WARN", code, message))

    def emit(self):
        if not self.items:
            print("OK")
        for level, code, message in self.items:
            print(f"{level} {code}: {message}")
        return 2 if any(level == "BLOCK" for level, _, _ in self.items) else 0


class Row:
    def __init__(self, row_id, index, tags, tagged):
        self.id = row_id
        self.index = index
        self.tags = tags
        self.tagged = tagged

    def values(self, key):
        return self.tags.get(key, [])

    def first(self, key, default=""):
        values = self.values(key)
        return values[0] if values else default


def run_git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def find_root(given):
    if given:
        return Path(given).resolve()
    return Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())


def read_text(path):
    return path.read_text(encoding="utf-8-sig")


def profile_line(root, label):
    path = root / "doctrine" / "profile.md"
    if not path.exists():
        return None
    pattern = re.compile(r"^\s*-\s*" + re.escape(label) + r"\s*:\s*(.+)$", re.IGNORECASE)
    for line in read_text(path).splitlines():
        match = pattern.match(line)
        if match:
            value = match.group(1).strip()
            if value.startswith("<"):
                return None
            return value
    return None


def profile_path(root, label, default):
    value = profile_line(root, label)
    if not value:
        return root / default
    quoted = re.search(r"`([^`]+)`", value)
    candidate = quoted.group(1) if quoted else value.split()[0]
    for base in (root, root / "doctrine"):
        if (base / candidate).exists():
            return base / candidate
    return root / default


def profile_threshold(root):
    value = profile_line(root, "Lineage audit threshold")
    if value:
        match = re.search(r"\d+", value)
        if match:
            return max(2, int(match.group(0)))
    return 3


def profile_kinds(root):
    kinds = dict(DEFAULT_KINDS)
    value = profile_line(root, "Ledger kinds")
    if value:
        for pair in re.findall(r"([A-Z]{1,3})\s*=\s*([a-z]+)", value):
            kinds[pair[0]] = pair[1]
    return kinds


def parse_tags(cell):
    text = cell.strip()
    if not text:
        return {}
    tags = {}
    for part in [piece.strip() for piece in text.split(";") if piece.strip()]:
        if "=" not in part:
            return None
        key, value = part.split("=", 1)
        key = key.strip()
        if key not in TAG_KEYS:
            return None
        tags[key] = [item.strip() for item in value.split(",") if item.strip()]
    return tags


def parse_ledger(path):
    if not path.exists():
        return None, {}, "\n"
    raw = path.read_bytes().decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines()
    rows = {}
    for index, line in enumerate(lines):
        match = ROW_ID.match(line)
        if not match:
            continue
        body = line.strip()
        if not body.endswith("|"):
            continue
        inner = body[1:-1]
        cut = inner.rfind(" | ")
        last = inner[cut + 3:] if cut >= 0 else ""
        tags = parse_tags(last)
        rows[match.group(1)] = Row(match.group(1), index, tags or {}, tags is not None)
    return lines, rows, newline


def kind_of(row, kinds):
    if row.values("kind"):
        return row.first("kind")
    return kinds.get(row.id.split("-")[0], "other")


def state_of(row):
    return row.first("state", "open")


def sections(text):
    found = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1)
            found[current] = []
        elif current is not None:
            found[current].append(line)
    return {name: "\n".join(body).strip() for name, body in found.items()}


def tokens(body):
    if not body or body.lower().startswith("none"):
        return []
    items = []
    for part in re.split(r"[,\n]", body):
        item = part.strip().lstrip("-").strip().strip("`").strip()
        if item and not item.lower().startswith("none"):
            items.append(item)
    return items


def table_under(body):
    rows = [line for line in body.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return [], []
    split = lambda line: [cell.strip() for cell in line.strip().strip("|").split("|")]
    header = split(rows[0])
    return header, [split(line) for line in rows[2:]]


class Task:
    def __init__(self, name, text):
        self.name = name
        self.text = text
        self.parts = sections(text)
        status = self.parts.get("Status", "")
        self.status = status.split(",")[0].split("\n")[0].strip()
        self.lineage = [item for item in tokens(self.parts.get("Lineage", "")) if LINEAGE_KEY.match(item)]
        self.bad_lineage = [item for item in tokens(self.parts.get("Lineage", "")) if not LINEAGE_KEY.match(item)]
        self.repairs = ANY_ID.findall(self.parts.get("Repairs", ""))
        superseded = tokens(self.parts.get("Supersedes", ""))
        self.supersedes = superseded[0].split()[0] if superseded else ""
        self.moves = self.parts.get("Moves", "")
        header, rows = table_under(self.parts.get("Criteria", ""))
        self.has_oracle_column = "Oracle" in header
        self.criteria = []
        if header:
            oracle_index = header.index("Oracle") if self.has_oracle_column else None
            for cells in rows:
                if not cells or not cells[0]:
                    continue
                oracle = cells[oracle_index] if oracle_index is not None and oracle_index < len(cells) else ""
                self.criteria.append((cells[0], oracle))
        cited = []
        for name in CITED_SECTIONS:
            cited.extend(ANY_ID.findall(self.parts.get(name, "")))
        self.cited = sorted(set(cited))
        self.readers_present = "Readers" in self.parts and bool(self.parts["Readers"])
        self.readers = parse_readers(self.parts.get("Readers", ""))
        self.scope_paths, self.scope_names = parse_scope(self.parts.get("Scope", ""))
        base = re.search(r"\b([0-9a-f]{40})\b", self.parts.get("Base", ""))
        self.base_trunk = base.group(1) if base else ""


def parse_readers(body):
    """Each bullet of a packet's Readers: its first backticked string, and the paths after 'not affected:'."""
    readers = []
    if not body or body.lower().startswith("none"):
        return readers
    for line in body.splitlines():
        text = line.strip()
        if not text.startswith(("-", "*")):
            continue
        ticks = re.findall(r"`([^`]+)`", text)
        if not ticks:
            continue
        excused = []
        marker = text.lower().find("not affected:")
        if marker >= 0:
            excused = [path.strip().rstrip("/") for path in re.findall(r"`([^`]+)`", text[marker:])]
        readers.append((ticks[0], excused))
    return readers


def parse_scope(body):
    """Paths named in Scope. A bare file name on a line resolves against the last directory named before it on that line."""
    paths, names = set(), set()
    for line in body.splitlines():
        last_dir = None
        for token in re.findall(r"`([^`]+)`", line):
            token = token.strip()
            if not token or " " in token:
                continue
            if "/" in token:
                path = token.rstrip("/")
                paths.add(path)
                last_dir = path if token.endswith("/") else path.rsplit("/", 1)[0]
            elif last_dir:
                paths.add(f"{last_dir}/{token}")
            else:
                names.add(token)
    return paths, names


def in_scope(path, paths, names):
    if path.rsplit("/", 1)[-1] in names:
        return True
    return any(path == entry or path.startswith(entry + "/") for entry in paths)


def check_readers(findings, root, task):
    if not task.readers_present:
        findings.block("readers", "the packet has no Readers section: every name it changes, with the string that finds its readers, or None")
        return
    if not task.readers:
        # A Readers section that names no string checks nothing, and would pass silently. It must either list the
        # strings that find each changed name's readers, or say "None" with its reason (the packet changes no name).
        body = task.parts.get("Readers", "").strip()
        if not body.lower().startswith("none"):
            findings.block(
                "readers-empty",
                "Readers names no backticked string: list every name the packet changes with the string that finds its "
                "readers, or write 'None.' with the reason no name changes",
            )
        return
    if not task.base_trunk:
        findings.block("readers-base", "no 40-character trunk commit in Base, so the reader grep cannot run")
        return
    for string, excused in task.readers:
        if string.startswith("<"):
            findings.block("readers", f"Readers holds a placeholder: `{string}`")
            continue
        result = subprocess.run(
            ["git", "-C", str(root), "grep", "-l", "-F", "-e", string, task.base_trunk, "--", ".", ":(exclude)doctrine/**"],
            capture_output=True, text=True,
        )
        if result.returncode not in (0, 1):
            findings.block("readers-grep", f"git grep for `{string}` at {task.base_trunk[:7]} failed: {result.stderr.strip()[:200]}")
            continue
        found = sorted({line.split(":", 1)[1] for line in result.stdout.splitlines() if ":" in line})
        print(f"READERS `{string}` at {task.base_trunk[:7]}: {', '.join(found) if found else 'none'}")
        for path in found:
            if in_scope(path, task.scope_paths, task.scope_names):
                continue
            if any(path == entry or path.startswith(entry + "/") for entry in excused):
                continue
            findings.block(
                "readers-outside",
                f"`{string}` is read by {path}, which is neither in Scope nor declared 'not affected:' with a reason",
            )


def load_tasks(root):
    folder = root / "doctrine" / "tasks"
    tasks = {}
    if folder.exists():
        for path in sorted(folder.glob("*.md")):
            tasks[path.stem] = Task(path.stem, read_text(path))
    return tasks


def parse_milestone(campaign_path):
    milestone = {"id": "", "regimes": [], "map": "", "oracles": [], "present": False}
    if not campaign_path.exists():
        return milestone
    inside = False
    for line in read_text(campaign_path).splitlines():
        if "Current milestone" in line:
            inside = True
            milestone["present"] = True
            continue
        if inside and re.match(r"^\s*\d+\.\s", line):
            break
        if not inside:
            continue
        field = re.match(r"^\s*-\s*(Id|Regime|Regime map|Oracles)\s*:\s*(.*)$", line)
        if not field:
            continue
        label, value = field.group(1), field.group(2).strip().strip("`")
        if label == "Id":
            milestone["id"] = value.split()[0] if value else ""
        elif label == "Regime":
            milestone["regimes"] = [item.strip().strip("`") for item in value.split(",") if item.strip()]
        elif label == "Regime map":
            found = None if value.lower().startswith("pending") else ANY_ID.match(value)
            milestone["map"] = found.group(1) if found else ""
        elif label == "Oracles":
            milestone["oracles"] = [item.strip().strip("`") for item in value.split(",") if item.strip()]
    return milestone


def lineage_events(rows, tasks, kinds):
    covered = set()
    for row in rows.values():
        if kind_of(row, kinds) == "audit" and state_of(row) in DONE_STATES:
            covered.update(row.values("covers"))
    events = defaultdict(list)
    for row in rows.values():
        if row.id in covered:
            continue
        keys = row.values("lineage")
        foundational = "foundational" in row.values("severity")
        if not keys:
            continue
        if kind_of(row, kinds) == "defect" or foundational:
            for key in keys:
                events[key].append((row.id, foundational))
    for task in tasks.values():
        if not task.supersedes:
            continue
        marker = f"task:{task.supersedes}"
        if marker in covered:
            continue
        for key in task.lineage:
            events[key].append((marker, False))
    return events


def audits_due(events, threshold):
    due = {}
    for key, found in events.items():
        if len(found) >= threshold or any(flag for _, flag in found):
            due[key] = found
    return due


def is_path(entry):
    return "/" in entry or re.search(r"\.[A-Za-z0-9]+$", entry) is not None


def stale_ids(rows):
    return {row.id for row in rows.values() if row.values("stale")}


def check_reference(findings, rows, reference_id, regimes, where):
    row = rows.get(reference_id)
    if row is None:
        findings.block("oracle-missing", f"{where}: reference {reference_id} has no ledger row")
        return
    if row.values("stale"):
        findings.block("oracle-stale", f"{where}: reference {reference_id} is stale; re-verify it first")
    validated = set(row.values("validated-in"))
    missing = [regime for regime in regimes if regime not in validated]
    if not validated:
        findings.block("oracle-unvalidated", f"{where}: reference {reference_id} has no validated-in regime")
    elif missing:
        findings.block(
            "oracle-regime",
            f"{where}: reference {reference_id} is not validated in {', '.join(missing)}",
        )


def check_oracle(findings, task, criterion, oracle, rows, regimes, criteria_ids):
    where = f"{task.name} {criterion}"
    if not oracle:
        findings.block("oracle-none", f"{where}: no oracle declared")
        return
    clauses = [clause.strip() for clause in oracle.split(";") if clause.strip()]
    text = " ".join(clauses)
    if not ORACLE_KIND.search(text):
        findings.block(
            "oracle-kind",
            f"{where}: oracle '{oracle}' names none of spec, exact:, analytic:, invariant:, reference:, relative, regression",
        )
    for match in re.finditer(r"reference:([A-Z]{1,3}-\d+)", text):
        check_reference(findings, rows, match.group(1), regimes, where)
    if re.search(r"\brelative\b", text):
        shares = re.search(r"shares=([^;]+)", oracle)
        covered = re.search(r"covered-by=([^;]+)", oracle)
        if not shares or not covered:
            findings.block(
                "blind-spot",
                f"{where}: a relative comparison names what both arms share (shares=) and the check that covers it (covered-by=)",
            )
        else:
            target = covered.group(1).strip()
            if target in criteria_ids:
                pass
            elif ANY_ID.fullmatch(target):
                row = rows.get(target)
                if row is None:
                    findings.block("blind-spot", f"{where}: covered-by {target} has no ledger row")
                elif row.values("stale"):
                    findings.block("blind-spot", f"{where}: covered-by {target} is stale")
            else:
                findings.block("blind-spot", f"{where}: covered-by {target} is neither a criterion nor a ledger row")
    if "excludes=" in oracle and "floor=" not in oracle:
        findings.block("coverage-floor", f"{where}: an exclusion rule needs a coverage floor (floor=)")


def reopen_trigger(line):
    found = REOPEN.search(line)
    return found.group(0).strip() if found else ""


def park_observable(line):
    found = OBSERVES.search(line)
    return found.group(1).strip() if found else ""


def check_park_records(findings, lines, rows):
    for row in rows.values():
        if state_of(row) != "parked":
            continue
        if not reopen_trigger(lines[row.index]):
            findings.warn("park-trigger", f"parked {row.id} has no reopen trigger in its row (a sentence starting 'Reopen if', 'Reopen when' or 'Reopen with')")
        elif not park_observable(lines[row.index]):
            findings.warn("park-observes", f"parked {row.id} has no 'Observes: ...' sentence stating literally what a result must report for its trigger to be checked")
        if not row.values("regime"):
            findings.warn("park-regime", f"parked {row.id} names no regime=, so no milestone check can see it")


def check_parks(findings, rows, milestone, kinds):
    if not milestone["regimes"]:
        return
    wanted = set(milestone["regimes"])
    for row in rows.values():
        if state_of(row) != "parked":
            continue
        overlap = wanted & set(row.values("regime"))
        if not overlap:
            continue
        bound_in = set(row.values("bound-in"))
        if milestone["id"] in bound_in or overlap <= bound_in:
            continue
        findings.block(
            "park-domain",
            f"parked {row.id} covers {', '.join(sorted(overlap))}, where milestone {milestone['id'] or '?'} runs, but its bound was not measured there: re-bound it there or reopen it",
        )


def check_milestone(findings, rows, milestone, kinds, strict):
    if not milestone["present"]:
        findings.warn("milestone", "the campaign file names no current milestone")
        return
    if not milestone["id"] or not milestone["regimes"]:
        (findings.block if strict else findings.warn)(
            "milestone-regime",
            "the current milestone declares no Id or Regime: run /doctrine:milestone",
        )
        return
    for oracle in milestone["oracles"]:
        for match in re.finditer(r"reference:([A-Z]{1,3}-\d+)", oracle):
            check_reference(findings, rows, match.group(1), milestone["regimes"], f"milestone {milestone['id']}")
    mapped = rows.get(milestone["map"]) if milestone["map"] else None
    if mapped is None:
        (findings.block if strict else findings.warn)(
            "regime-map",
            f"milestone {milestone['id']} has no regime map: run /doctrine:milestone",
        )
    elif milestone["id"] not in mapped.values("regime-map"):
        (findings.block if strict else findings.warn)(
            "regime-map",
            f"regime map {mapped.id} is not tagged regime-map={milestone['id']}",
        )
    elif mapped.values("stale"):
        (findings.block if strict else findings.warn)(
            "regime-map", f"regime map {mapped.id} is stale: rerun it"
        )
    check_parks(findings, rows, milestone, kinds)


def report_due(findings, due, keys=None):
    for key, found in sorted(due.items()):
        if keys is not None and key not in keys:
            continue
        foundational = [item for item, flag in found if flag]
        reason = (
            f"foundational finding {', '.join(foundational)}"
            if foundational
            else f"{len(found)} related failures: {', '.join(item for item, _ in found)}"
        )
        findings.block("audit-due", f"lineage {key}: {reason}; run /doctrine:audit {key}")


def context(root):
    ledger_path = profile_path(root, "Ledger", "doctrine/ledger.md")
    campaign_path = profile_path(root, "Campaign file", "doctrine/campaign.md")
    lines, rows, newline = parse_ledger(ledger_path)
    return {
        "ledger_path": ledger_path,
        "lines": lines,
        "rows": rows,
        "newline": newline,
        "tasks": load_tasks(root),
        "milestone": parse_milestone(campaign_path),
        "threshold": profile_threshold(root),
        "kinds": profile_kinds(root),
    }


def normal(text):
    return re.sub(r"\s+", " ", text.strip().strip("`").strip().lower())


def model_named(root):
    return profile_line(root, "Model") is not None


def parse_model(root):
    path = profile_path(root, "Model", "doctrine/model.md")
    if not path.exists():
        return None
    parts = sections(read_text(path))
    routes = []
    _, rows = table_under(parts.get("Routes", ""))
    for cells in rows:
        if len(cells) >= 3 and cells[0]:
            routes.append({"name": cells[0], "bound": cells[1], "status": cells[2]})
    _, goal_rows = table_under(parts.get("Goal", ""))
    terms = [cells[0] for cells in goal_rows if cells and cells[0]]
    items = []
    for line in parts.get("Next", "").splitlines():
        if re.match(r"^\s*\d+\.\s", line):
            items.append(line.strip())
        elif items and line.strip() and line[:1].isspace():
            items[-1] += " " + line.strip()
    return {"path": path, "routes": routes, "terms": terms, "next": items}


def find_route(model, name):
    wanted = normal(name)
    for route in model["routes"]:
        if normal(route["name"]) == wanted:
            return route
    for route in model["routes"]:
        if normal(route["name"]).startswith(wanted):
            return route
    return None


def names_term(text, terms):
    found = normal(text)
    return any(normal(term) in found for term in terms)


def check_route_and_prediction(findings, root, task):
    if not model_named(root):
        return
    model = parse_model(root)
    if model is None:
        findings.block("model", "the profile names a Model file that does not exist")
        return
    lines = [line for line in task.parts.get("Route", "").splitlines() if line.strip()]
    if not lines:
        findings.block("route-none", "the packet names no Route: a row of the model's Routes table")
    else:
        route = find_route(model, lines[0])
        if route is None:
            findings.block("route-unknown", f"the Route '{lines[0].strip()}' is no row of the model's Routes table")
        elif normal(route["status"]).startswith("falsified"):
            findings.block("route-falsified", f"the route '{route['name']}' is falsified ({route['status']}): reset the route first")
        elif not normal(route["bound"]) or normal(route["bound"]).startswith("unknown"):
            findings.block("route-unbounded", f"the route '{route['name']}' has no bound at the milestone's scale: measure the bound before building on it")
    prediction = re.search(r"Predicts:\s*(.+)$", task.moves, re.MULTILINE | re.IGNORECASE)
    if not prediction:
        findings.block("prediction-none", "Moves has no 'Predicts: <goal term>: <now> -> <after>' line")
    elif not names_term(prediction.group(1), model["terms"]):
        findings.block("prediction-term", "the prediction names no term of the model's Goal table")


def model_problems(findings, root, model, base=None, head=None, staged=False):
    ledger = profile_path(root, "Ledger", "doctrine/ledger.md")
    if base or staged:
        span = ["--cached"] if staged else [base, head or "HEAD"]
        relative_ledger = ledger.relative_to(root).as_posix()
        relative_model = model["path"].relative_to(root).as_posix()
        added = [line for line in run_git(root, "diff", "-U0", *span, "--", relative_ledger).splitlines()
                 if re.match(r"^\+\|\s*[ED]-\d+\s*\|", line)]
        changed = run_git(root, "diff", "--name-only", *span).split()
        if added and relative_model not in changed:
            ids = ", ".join(re.match(r"^\+\|\s*([ED]-\d+)", line).group(1) for line in added)
            findings.block("model-stale", f"{ids} entered the ledger without an update to {relative_model}: every result updates the model")
        for line in added:
            ident = re.match(r"^\+\|\s*([ED]-\d+)", line).group(1)
            if ident.startswith("E-") and not re.search(r"\bprior:", line, re.IGNORECASE):
                findings.block("prior-none", f"{ident} cites no prior rows: search the ledger for its method and question first, then name what it extends ('prior: <ids>' or 'prior: none (searched: <terms>)')")
    if not model["next"]:
        findings.block("plan-empty", "the model's Next is empty: the next action comes from the model before any other work")
    for item in model["next"]:
        if not re.search(r"moves:", item, re.IGNORECASE):
            findings.block("next-moves", f"Next item '{item[:60]}' names no goal term it moves ('moves: <term>')")


def command_model(root, args):
    findings = Findings()
    model = parse_model(root)
    if model is None:
        if model_named(root):
            findings.block("model", "the profile names a Model file that does not exist")
        else:
            findings.warn("model", "the profile names no Model file")
        return findings.emit()
    model_problems(findings, root, model, args.base, args.head, args.staged)
    return findings.emit()


def command_triggers(root, args):
    ctx = context(root)
    findings = Findings()
    if ctx["lines"] is None:
        findings.warn("ledger", f"no ledger at {ctx['ledger_path']}: lineage, stale and park triggers are inactive")
        return findings.emit()
    events = lineage_events(ctx["rows"], ctx["tasks"], ctx["kinds"])
    due = audits_due(events, ctx["threshold"])
    scope = None
    if args.task:
        task = ctx["tasks"].get(args.task)
        if task is None:
            raise SystemExit(f"no packet doctrine/tasks/{args.task}.md")
        scope = set(task.lineage)
        for defect in task.repairs:
            row = ctx["rows"].get(defect)
            if row:
                scope.update(row.values("lineage"))
    report_due(findings, due, scope)
    settings = routing_settings(root)
    if scope and not settings["off"]:
        check_decisions(findings, ctx, settings, scope)
    check_milestone(findings, ctx["rows"], ctx["milestone"], ctx["kinds"], strict=False)
    if ctx["lines"] is not None:
        check_park_records(findings, ctx["lines"], ctx["rows"])
    stale = sorted(stale_ids(ctx["rows"]))
    if stale:
        findings.warn("stale", f"{len(stale)} stale rows, not citable until re-verified: {', '.join(stale)}")
    return findings.emit()


def command_accept(root, args):
    ctx = context(root)
    rows, milestone = ctx["rows"], ctx["milestone"]
    findings = Findings()
    task = ctx["tasks"].get(args.task)
    if task is None:
        raise SystemExit(f"no packet doctrine/tasks/{args.task}.md")
    moves_milestone = bool(milestone["id"]) and milestone["id"] in task.moves
    regimes = milestone["regimes"] if moves_milestone else []
    if ctx["lines"] is None:
        findings.warn("ledger", f"no ledger at {ctx['ledger_path']}: lineage, stale and park checks are skipped")
    if not task.lineage:
        findings.block("lineage", "the packet names no lineage (## Lineage: layer:, regime:, invariant:, criterion: keys)")
    for item in task.bad_lineage:
        findings.block("lineage", f"'{item}' is not a lineage key (layer:, regime:, invariant: or criterion:)")
    stale = stale_ids(rows)
    for cited in task.cited:
        if cited in stale:
            findings.block("stale", f"the packet cites {cited}, which is stale: re-verify it first")
    if not task.has_oracle_column:
        findings.block("oracle-none", "the Criteria table has no Oracle column")
    criteria_ids = {criterion for criterion, _ in task.criteria}
    for criterion, oracle in task.criteria:
        check_oracle(findings, task, criterion, oracle, rows, regimes, criteria_ids)
    oracles = " ".join(oracle for _, oracle in task.criteria)
    for defect in task.repairs:
        row = rows.get(defect)
        if row is None:
            findings.block("repairs", f"Repairs names {defect}, which has no ledger row")
            continue
        for key in row.values("lineage"):
            if key.startswith("invariant:") and key not in oracles:
                findings.block(
                    "invariant-first",
                    f"{defect} breaks {key}: a criterion must use oracle {key} over the regime, not only the first mechanism seen",
                )
    if task.supersedes and task.supersedes not in ctx["tasks"]:
        findings.warn("supersedes", f"Supersedes names {task.supersedes}, which has no packet")
    check_readers(findings, root, task)
    check_route_and_prediction(findings, root, task)
    if ctx["lines"] is not None:
        events = lineage_events(rows, ctx["tasks"], ctx["kinds"])
        scope = set(task.lineage)
        for defect in task.repairs:
            row = rows.get(defect)
            if row:
                scope.update(row.values("lineage"))
        report_due(findings, audits_due(events, ctx["threshold"]), scope)
        settings = routing_settings(root)
        if not settings["off"]:
            check_decisions(findings, ctx, settings, scope)
    if moves_milestone:
        check_milestone(findings, rows, milestone, ctx["kinds"], strict=True)
    elif milestone["present"] and not milestone["id"]:
        findings.warn("milestone-regime", "the current milestone has no Id, so the packet's Moves cannot be matched: run /doctrine:milestone")
    return findings.emit()


def command_milestone(root, args):
    ctx = context(root)
    findings = Findings()
    check_milestone(findings, ctx["rows"], ctx["milestone"], ctx["kinds"], strict=True)
    return findings.emit()


def command_merge(root, args):
    ctx = context(root)
    findings = Findings()
    if ctx["lines"] is None:
        findings.warn("ledger", f"no ledger at {ctx['ledger_path']}: nothing to mark stale")
        return findings.emit()
    changed = [
        path.strip().replace("\\", "/")
        for path in run_git(root, "diff", "--name-only", args.base, args.head).splitlines()
        if path.strip()
    ]
    rows = ctx["rows"]
    direct = set()
    for row in rows.values():
        if row.values("stale"):
            continue
        for entry in row.values("rests-on"):
            entry_path = entry.replace("\\", "/").rstrip("/")
            if is_path(entry) and any(path == entry_path or path.startswith(entry_path + "/") for path in changed):
                direct.add(row.id)
    marked = set(direct)
    grew = True
    while grew:
        grew = False
        for row in rows.values():
            if row.id in marked or row.values("stale"):
                continue
            if any(entry in marked for entry in row.values("rests-on")):
                marked.add(row.id)
                grew = True
    if not marked:
        print(f"OK: the merge {args.base[:7]}..{args.head[:7]} touches nothing a ledger row rests on")
        return 0
    head = run_git(root, "rev-parse", "--short", args.head).strip()
    for row_id in sorted(marked):
        how = "rests on a changed path" if row_id in direct else "rests on a stale row"
        print(f"STALE {row_id}: {how}")
    if args.apply:
        lines = ctx["lines"]
        for row_id in marked:
            row = rows[row_id]
            line = lines[row.index].rstrip()
            inner = line[:-1].rstrip()
            cut = inner.rfind(" | ")
            last = inner[cut + 3:].strip()
            addition = f"stale={head}"
            last = f"{last}; {addition}" if last else addition
            lines[row.index] = f"{inner[:cut]} | {last} |"
        ctx["ledger_path"].write_bytes((ctx["newline"].join(lines) + ctx["newline"]).encode("utf-8"))
        print(f"marked {len(marked)} rows stale={head} in {ctx['ledger_path']}")
    return 0


def command_cites(root, args):
    ctx = context(root)
    findings = Findings()
    path = Path(args.file)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        raise SystemExit(f"no file {path}")
    cited = sorted(set(ANY_ID.findall(read_text(path))))
    rows = ctx["rows"]
    stale = stale_ids(rows)
    scope = set()
    for cited_id in cited:
        if cited_id in stale:
            findings.block("stale", f"{path.name} cites {cited_id}, which is stale: re-verify it first")
        row = rows.get(cited_id)
        if row is not None and kind_of(row, ctx["kinds"]) == "defect":
            scope.update(row.values("lineage"))
    if scope:
        events = lineage_events(rows, ctx["tasks"], ctx["kinds"])
        report_due(findings, audits_due(events, ctx["threshold"]), scope)
    return findings.emit()


def command_lineage(root, args):
    ctx = context(root)
    events = lineage_events(ctx["rows"], ctx["tasks"], ctx["kinds"])
    threshold = ctx["threshold"]
    if not events:
        print("no tagged failures")
        return 0
    for key, found in sorted(events.items(), key=lambda item: (-len(item[1]), item[0])):
        flag = " foundational" if any(f for _, f in found) else ""
        due = " AUDIT DUE" if len(found) >= threshold or flag else ""
        print(f"{key}: {len(found)}/{threshold}{flag}{due} ({', '.join(item for item, _ in found)})")
    return 0


# Routing (DESIGN.md, Progression, Routing): the permitted next action at a decision boundary,
# from hard facts only (the diff, the profile, the ledger, the packet). No model is asked.
ROUTE_ACTIONS = ("mechanical", "probe", "repair", "investigate", "complete")
ROUTE_ORDER = {"fast": 0, "bounded": 1, "doctrine": 2, "reset": 3}
DEFAULT_CONSEQUENTIAL = (
    r"threshold|toleran|timeout|deadline|limit|quota|budget|baseline|expected|expect\(|assert"
    r"|retr(?:y|ies)|\bmax|\bmin|auth|permission|policy|grant|privilege|\brole"
)
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
OPERATOR = re.compile(
    r"==|!=|<=|>=|=>|&&|\|\||(?<![<>=!-])[<>](?![<>=])|!(?!=)"
    r"|\b(?:and|or|not|is|in|true|false|True|False|null|None|nil|undefined)\b"
)
STRING = re.compile(r"(['\"`])(?:\\.|(?!\1).)*\1")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\S")
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COMMENT = re.compile(r"^\s*(#|//|--|\*|/\*|<!--)")
TEST_PATH = re.compile(r"(^|/)(tests?|spec|__tests__)(/|$)|[._-](test|spec)\.[A-Za-z]+$")
PROSE_SUFFIXES = (".md", ".txt", ".rst", ".adoc")


def routing_settings(root):
    first = (profile_line(root, "Routing") or "on").split()[0].strip("`.;,").lower()
    never = [
        item.strip().strip("`")
        for item in re.split(r"[,\s]+", profile_line(root, "Routing never fast") or "")
        if item.strip().strip("`")
    ]

    def count(label, default):
        match = re.search(r"\d+", profile_line(root, label) or "")
        return max(1, int(match.group(0))) if match else default

    words = profile_line(root, "Routing consequential words")
    return {
        "off": first in ("off", "disabled", "none"),
        "never": never,
        "resets": count("Routing reset after", 2),
        "probes": count("Routing probe budget", 1),
        "words": re.compile(words.strip("`") if words else DEFAULT_CONSEQUENTIAL, re.IGNORECASE),
    }


def decision_rows(ctx, decision):
    return sorted(
        (row for row in ctx["rows"].values() if decision in row.values("lineage")),
        key=lambda row: row.index,
    )


def decision_budget(ctx, decision):
    """Failed repair cycles since the last reset that changed something, and the resets that changed nothing."""
    failed, unchanged, inconclusive, decisive = 0, [], [], []
    for row in decision_rows(ctx, decision):
        kind = kind_of(row, ctx["kinds"])
        outcome = row.first("outcome")
        if kind == "reset":
            if row.values("changed"):
                failed = 0
            else:
                unchanged.append(row.id)
        elif kind == "repair":
            if outcome == "failed":
                failed += 1
            elif outcome in ("fixed", "informative"):
                failed = 0
        if kind == "probe" and outcome == "inconclusive":
            inconclusive.append(row.id)
        if outcome == "decisive":
            decisive.append(row.id)
    return {"failed": failed, "unchanged": unchanged, "inconclusive": inconclusive, "decisive": decisive}


def check_decisions(findings, ctx, settings, keys):
    """The reset trigger, enforced wherever a command names the decision's lineage."""
    for key in sorted(k for k in keys if k.startswith("decision:")):
        budget = decision_budget(ctx, key)
        if budget["unchanged"]:
            findings.warn(
                "reset-unchanged",
                f"{key}: {', '.join(budget['unchanged'])} records a reset with no changed= "
                "(hypothesis, strategy, scope or rationale), so it clears nothing",
            )
        if budget["failed"] >= settings["resets"]:
            findings.block(
                "reset-due",
                f"{key}: {budget['failed']} unsuccessful repair cycles with no new discriminating evidence since the "
                f"last reset; run the configured reset or independent decision before another attempt, and record "
                f"kind=reset; lineage={key}; changed=<hypothesis|strategy|scope|rationale>",
            )


def changed_paths(root, base, head):
    if base and head:
        tracked = run_git(root, "diff", "--name-only", base, head).splitlines()
        untracked = []
    else:
        tracked = run_git(root, "diff", "--name-only", base or "HEAD").splitlines()
        untracked = run_git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return [p.strip().replace("\\", "/") for p in tracked if p.strip()], [p.strip() for p in untracked if p.strip()]


def code_part(line):
    """The line without a trailing # or // comment that sits outside any quotes."""
    for marker in (" #", "\t#", "//"):
        cut = line.find(marker)
        if cut >= 0 and line[:cut].count('"') % 2 == 0 and line[:cut].count("'") % 2 == 0:
            line = line[:cut]
    return line


def line_problem(path, old, new, words):
    if re.sub(r"\s+", "", old) == re.sub(r"\s+", "", new):
        return None
    if not path.lower().endswith(PROSE_SUFFIXES) and not TEST_PATH.search(path):
        if re.sub(r"\s+", "", code_part(old)) == re.sub(r"\s+", "", code_part(new)):
            return None
        old, new = code_part(old), code_part(new)
    if TEST_PATH.search(path):
        return "changes a test, which can change an expected result"
    if path.lower().endswith(PROSE_SUFFIXES):
        return "changes prose, which can change what a rule or record says"
    if COMMENT.match(old) and COMMENT.match(new):
        return None
    if [m.group(0) for m in STRING.finditer(old)] != [m.group(0) for m in STRING.finditer(new)]:
        return "changes a string literal"
    if NUMBER.findall(old) != NUMBER.findall(new):
        return "changes a number"
    if OPERATOR.findall(old) != OPERATOR.findall(new):
        return "changes an operator, a condition or a literal"
    if words.search(old) or words.search(new):
        return "touches a consequential term"
    before, after = IDENT.findall(old), IDENT.findall(new)
    if len(before) == len(after) and all(
        a == b or (IDENTIFIER.match(a) and IDENTIFIER.match(b)) for a, b in zip(before, after)
    ):
        return None
    return "changes code beyond formatting or a rename"


def diff_problems(root, settings, base, head):
    """Why a change is not mechanical; an empty list means formatting or a consistent rename only."""
    tracked, untracked = changed_paths(root, base, head)
    problems = []
    if not tracked and not untracked:
        return ["no change to route"], []
    for path in untracked:
        problems.append(f"{path}: adds a file")
    renames = {}
    for path in tracked:
        if any(fnmatch.fnmatchcase(path, glob) for glob in settings["never"]):
            problems.append(f"{path}: the profile never lets a change here be fast")
            continue
        args = ["diff", "-U0", "--no-color", "--no-ext-diff"] + ([base, head] if base and head else [base or "HEAD"])
        text = run_git(root, *args, "--", path)
        if re.search(r"^(new|deleted) file mode", text, re.MULTILINE):
            problems.append(f"{path}: adds or removes a file")
            continue
        for hunk in re.split(r"^@@[^\n]*@@[^\n]*$", text, flags=re.MULTILINE)[1:]:
            removed = [l[1:] for l in hunk.splitlines() if l.startswith("-") and not l.startswith("---")]
            added = [l[1:] for l in hunk.splitlines() if l.startswith("+") and not l.startswith("+++")]
            if len(removed) != len(added) and any(l.strip() for l in removed + added):
                problems.append(f"{path}: adds or removes lines")
                continue
            for old, new in zip(removed, added):
                problem = line_problem(path, old, new, settings["words"])
                if problem:
                    problems.append(f"{path}: {problem}")
                    continue
                for a, b in zip(IDENT.findall(old), IDENT.findall(new)):
                    if a != b and renames.setdefault(a, b) != b:
                        problems.append(f"{path}: renames {a} inconsistently")
    return sorted(set(problems)), tracked + untracked


def route_obligations(ctx, task, decision):
    rows, items = ctx["rows"], []
    if task is not None:
        if not task.status.lower().startswith("merged"):
            items.append(f"{task.name}: status '{task.status or 'none'}'; its criteria, checks and review stay required")
        for defect in task.repairs:
            row = rows.get(defect)
            if row is not None and state_of(row) not in DONE_STATES:
                items.append(f"{defect}: {state_of(row)}, repaired only when its criterion passes")
        stale = stale_ids(rows)
        items.extend(f"{cited}: stale, not citable until re-verified" for cited in task.cited if cited in stale)
    if decision:
        for row in decision_rows(ctx, decision):
            if kind_of(row, ctx["kinds"]) == "defect" and state_of(row) not in DONE_STATES:
                items.append(f"{row.id}: {state_of(row)}, in {decision}")
    return sorted(set(items))


def unpushed_trunk(root):
    rule = profile_line(root, "Push")
    if not rule or re.match(r"(none|no|never)\b", rule, re.IGNORECASE) or not re.search(r"\bpush\b", rule, re.IGNORECASE):
        return None
    quoted = re.search(r"`([^`]+)`", profile_line(root, "Trunk") or "")
    trunk = quoted.group(1) if quoted else "main"
    remote = "origin"
    result = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--count", f"{remote}/{trunk}..{trunk}"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    ahead = int(result.stdout.strip() or 0)
    return (trunk, remote, ahead, rule) if ahead else None


def route_state(root, ctx, task_name):
    digest = hashlib.sha256()
    paths = [ctx["ledger_path"], root / "doctrine" / "profile.md"]
    if task_name:
        paths.append(root / "doctrine" / "tasks" / f"{task_name}.md")
    for path in paths:
        digest.update(path.read_bytes() if path.exists() else b"-")
    digest.update(run_git(root, "rev-parse", "HEAD").encode())
    digest.update(run_git(root, "diff", "HEAD").encode())
    return digest.hexdigest()[:12]


def evaluate_route(root, ctx, settings, decision, action, task, cause, base, head):
    findings, why, confirm = Findings(), [], []
    route = "doctrine"
    rows = ctx["rows"]
    scope = {decision} if decision else set()
    if task is not None:
        scope.update(task.lineage)
        for defect in task.repairs:
            row = rows.get(defect)
            if row:
                scope.update(row.values("lineage"))
    if ctx["lines"] is not None:
        report_due(findings, audits_due(lineage_events(rows, ctx["tasks"], ctx["kinds"]), ctx["threshold"]), scope)
    budget = decision_budget(ctx, decision) if decision else None
    if budget and budget["unchanged"]:
        findings.warn("reset-unchanged", f"{decision}: {', '.join(budget['unchanged'])} records a reset with no changed=, so it clears nothing")
    obligations = route_obligations(ctx, task, decision)
    owed = unpushed_trunk(root)
    if owed:
        trunk, remote, ahead, rule = owed
        plural = "" if ahead == 1 else "s"
        findings.warn("unpushed", f"{trunk} is {ahead} commit{plural} ahead of {remote}/{trunk}; the profile says: {rule}")
        obligations.append(f"push {trunk} to {remote} ({ahead} ahead)")
    if budget and budget["failed"] >= settings["resets"] and action != "complete":
        route = "reset"
        check_decisions(findings, ctx, settings, {decision})
        why.append(f"{budget['failed']} unsuccessful repair cycles on {decision}; the next step is a reset, not a third attempt")
    elif budget and budget["decisive"] and action in ("probe", "investigate"):
        findings.block("answered", f"{decision} is answered by {', '.join(budget['decisive'])}: end this branch and continue with the obligations below")
        why.append("the governing question already has decisive evidence")
    elif action == "probe":
        if not decision:
            why.append("a probe needs its decision key, so its budget follows the decision across tasks")
        elif budget and len(budget["inconclusive"]) >= settings["probes"]:
            findings.block("probe-exhausted", f"{decision}: {', '.join(budget['inconclusive'])} already ended inconclusive; continue by the reasoning path, not another cheap probe")
            why.append("the bounded probe budget is spent")
        else:
            route = "bounded"
            why.append("one probe: state the decision, its alternatives and how each outcome changes the next action")
            confirm.append(f"record the probe as kind=probe; lineage={decision}; outcome=<decisive|inconclusive>")
    elif action == "mechanical":
        problems = []
        if not cause:
            problems.append("no established cause: --cause names the diagnostic log or the ledger row")
        elif ANY_ID.fullmatch(cause):
            if cause not in rows:
                problems.append(f"the cause {cause} has no ledger row")
            elif cause in stale_ids(rows):
                problems.append(f"the cause {cause} is stale")
        elif not (root / cause).exists() and not Path(cause).exists():
            problems.append(f"the cause {cause} is not a file or a ledger row")
        diff, paths = diff_problems(root, settings, base, head)
        problems += diff
        if problems:
            why.extend(f"not mechanical: {problem}" for problem in problems)
        else:
            route = "fast"
            why.append(f"an established cause ({cause}) and a formatting or rename-only change")
            confirm.append(f"run the smallest check that covers {', '.join(paths)}; the packet's own checks still run before it merges")
    elif action == "repair":
        why.append("a behavioural repair gets substantive validation")
        if decision:
            confirm.append(f"record the cycle as kind=repair; lineage={decision}; outcome=<fixed|failed|informative>")
    elif action == "investigate":
        why.append("new semantics, a failed criterion, unexpected behaviour or uncertain evidence")
    elif action == "complete":
        route = "doctrine" if obligations else "fast"
        why.append("the branch may end; completing an investigation accepts nothing" if obligations else "nothing named remains open")
    if any(level == "BLOCK" for level, code, _ in findings.items if code not in ("answered",)) and ROUTE_ORDER[route] < ROUTE_ORDER["doctrine"]:
        route = "doctrine"
        why.append("a hard escalation holds")
    return route, why, obligations, confirm, findings


def command_route(root, args):
    settings = routing_settings(root)
    if settings["off"]:
        print("ROUTE off: the profile turns routing off; the existing workflow applies")
        return 0
    ctx = context(root)
    task = None
    if args.task:
        task = ctx["tasks"].get(args.task)
        if task is None:
            raise SystemExit(f"no packet doctrine/tasks/{args.task}.md")
    decision = args.decision
    if not decision and task is not None:
        keys = [key for key in task.lineage if key.startswith("decision:")]
        decision = keys[0] if len(keys) == 1 else None
    if decision and not decision.startswith("decision:"):
        decision = f"decision:{decision}"
    state = route_state(root, ctx, args.task)
    route, why, obligations, confirm, findings = evaluate_route(
        root, ctx, settings, decision, args.action, task, args.cause, args.base, args.head
    )
    if args.expect_state and args.expect_state != state:
        findings.block("stale-route", f"the state changed since the route was computed ({args.expect_state} -> {state}): route again")
        if ROUTE_ORDER[route] < ROUTE_ORDER["doctrine"]:
            route = "doctrine"
    print(f"ROUTE {route} (decision={decision or 'none'}; action={args.action})")
    for line in why:
        print(f"WHY {line}")
    for line in obligations:
        print(f"OPEN {line}")
    for line in confirm:
        print(f"CONFIRM {line}")
    print(f"STATE {state}")
    if args.log:
        log = root / "doctrine" / "logs" / "routing.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        codes = ",".join(code for _, code, _ in findings.items) or "ok"
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} state={state} decision={decision or 'none'} action={args.action} route={route} checks={codes} why={' / '.join(why)}\n")
    return findings.emit()


def main():
    parser = argparse.ArgumentParser(prog="doctrine_check")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    triggers = sub.add_parser("triggers")
    triggers.add_argument("--task")
    accept = sub.add_parser("accept")
    accept.add_argument("task")
    sub.add_parser("milestone")
    merge = sub.add_parser("merge")
    merge.add_argument("task")
    merge.add_argument("--base", required=True)
    merge.add_argument("--head", required=True)
    merge.add_argument("--apply", action="store_true")
    sub.add_parser("lineage")
    model = sub.add_parser("model")
    model.add_argument("--base")
    model.add_argument("--head")
    model.add_argument("--staged", action="store_true")
    cites = sub.add_parser("cites")
    cites.add_argument("file")
    route = sub.add_parser("route")
    route.add_argument("--action", required=True, choices=ROUTE_ACTIONS)
    route.add_argument("--decision")
    route.add_argument("--task")
    route.add_argument("--cause")
    route.add_argument("--base")
    route.add_argument("--head")
    route.add_argument("--expect-state", dest="expect_state")
    route.add_argument("--log", action="store_true")
    args = parser.parse_args()
    root = find_root(args.root)
    handlers = {
        "triggers": command_triggers,
        "accept": command_accept,
        "milestone": command_milestone,
        "merge": command_merge,
        "lineage": command_lineage,
        "cites": command_cites,
        "route": command_route,
        "model": command_model,
    }
    sys.exit(handlers[args.command](root, args))


if __name__ == "__main__":
    main()
