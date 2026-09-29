import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doctrine_check as dc

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
PLUGIN = Path(__file__).resolve().parent.parent
BANDS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01)]


def api_key():
    token = os.environ.get("TYPESAFE_API_KEY")
    if token:
        return token
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return winreg.QueryValueEx(key, "TYPESAFE_API_KEY")[0]
        except OSError:
            pass
    raise SystemExit("TYPESAFE_API_KEY is not set")


def call(state, questions, model):
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode("utf-8")
    delay = 1.0
    for attempt in range(6):
        request = urllib.request.Request(
            ENDPOINT,
            data=body,
            headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code in (429, 529) and attempt < 5:
                time.sleep(delay)
                delay *= 2
                continue
            raise SystemExit(f"TypeSafe answered {error.code}: {error.read().decode('utf-8', 'replace')[:300]}")
    raise SystemExit("TypeSafe kept refusing the request")


def specs():
    return json.loads((PLUGIN / "rules" / "judgments.json").read_text(encoding="utf-8"))


def vocabulary(root):
    path = root / "doctrine" / "judgments.json"
    if not path.exists():
        raise SystemExit(f"no project vocabulary at {path}: list each lineage dimension's keys with a description")
    return json.loads(path.read_text(encoding="utf-8"))


def ledger(root):
    lines, rows, _ = dc.parse_ledger(dc.profile_path(root, "Ledger", "doctrine/ledger.md"))
    if lines is None:
        raise SystemExit("no ledger")
    return lines, rows


def cells(line):
    inner = line.strip()[1:-1]
    return [cell.strip() for cell in inner.split(" | ")]


def observation(lines, row):
    parts = cells(lines[row.index])
    return parts[1] if len(parts) > 1 else ""


def trigger_text(lines, row):
    found = dc.reopen_trigger(lines[row.index])
    if found:
        return found
    parts = cells(lines[row.index])
    status = parts[2] if len(parts) > 2 else ""
    found = re.search(r"([Rr]eopen[^.;]*(?:[.;][^.;]*){0,2})", status)
    return found.group(1).strip() if found else status


def confidence_of(answer):
    if "confidence" in answer:
        return float(answer["confidence"])
    probability = float(answer.get("noul", 0.5))
    return abs(2.0 * probability - 1.0)


def questions_for(judgment, spec, vocab):
    if judgment == "J1":
        built = {}
        for dimension in spec["dimensions"]:
            options = dict(vocab.get(dimension, {}))
            for name, text in spec["extra"].items():
                options[name] = text.format(dimension=dimension)
            built[dimension] = {
                "type": "choice",
                "instructions": spec["instructions"].format(dimension=dimension),
                "criteria": options,
            }
        return built
    if spec["primitive"] == "noul":
        return {judgment: {"type": "noul", "instructions": spec["instructions"], "criteria": spec["criteria"]}}
    return {judgment: {"type": "choice", "instructions": spec["instructions"], "criteria": spec["criteria"]}}


def label_of(judgment, spec, answer):
    if spec["primitive"] == "noul":
        return spec["labels"]["true" if float(answer.get("noul", 0.0)) >= 0.5 else "false"]
    return answer.get("choice", "")


def truth_for(judgment, row, dimension):
    if judgment == "J1":
        keys = [key.split(":", 1)[1] for key in row.values("lineage") if key.startswith(dimension + ":")]
        return keys[0] if keys else "none"
    if judgment == "J2":
        return "foundational" if "foundational" in row.values("severity") else "not-foundational"
    return ""


def dependency_facts(lines, rows, row):
    named = []
    for cited in sorted(set(dc.ANY_ID.findall(observation(lines, row)))):
        other = rows.get(cited)
        if other is None or cited == row.id:
            continue
        named.append({"id": cited, "kind": dc.kind_of(other, dc.DEFAULT_KINDS), "summary": observation(lines, other)[:160]})
    paths = {entry for entry in row.values("rests-on") if dc.is_path(entry)}
    resting = sorted(
        other.id
        for other in rows.values()
        if other.id != row.id and paths & {entry for entry in other.values("rests-on") if dc.is_path(entry)}
    )
    dependents = sorted(other.id for other in rows.values() if row.id in other.values("rests-on"))
    return {
        "finding": observation(lines, row),
        "rows the finding names": named,
        "results and decisions resting on the same code": resting,
        "rows resting on this finding": dependents,
    }


def state_for(judgment, lines, row, rows=None):
    if judgment == "J7":
        return trigger_text(lines, row)
    if judgment == "J2" and rows is not None:
        return dependency_facts(lines, rows, row)
    return observation(lines, row)


def labels(root):
    path = root / "doctrine" / "judgment-labels.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def judge(root, judgment, row_id, reasoning=None, log=True, state=None, questions=None):
    spec = specs()["judgments"][judgment]
    model = specs()["model"]
    if questions is None:
        lines, rows = ledger(root)
        vocab = vocabulary(root) if judgment == "J1" else {}
        if state is None:
            row = rows.get(row_id)
            if row is None:
                raise SystemExit(f"no ledger row {row_id}")
            state = state_for(judgment, lines, row, rows)
        questions = questions_for(judgment, spec, vocab)
    result = call(state, questions, model)
    records = []
    for question, answer in result["answers"].items():
        label = label_of(judgment, spec, answer)
        confidence = confidence_of(answer)
        unless = spec.get("escalate_unless")
        escalated = (
            confidence < spec["threshold"]
            or label in spec.get("escalate", [])
            or (unless is not None and label not in unless)
        )
        record = {
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
            "judgment": judgment,
            "row": row_id,
            "question": question,
            "label": label,
            "confidence": round(confidence, 4),
            "probabilities": answer.get("probabilities", {"noul": answer.get("noul")}),
            "escalate": escalated,
            "reasoning": reasoning(question) if callable(reasoning) else reasoning,
            "model": result.get("model", model),
            "spec_version": specs()["version"],
        }
        records.append(record)
    if log:
        path = root / "doctrine" / "judgments.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
    return records


def command_ask(root, args):
    for record in judge(root, args.judgment, args.row, args.reasoning, log=not args.no_log):
        flag = "ESCALATE" if record["escalate"] else "ok"
        agree = ""
        if record["reasoning"]:
            agree = " agree" if record["reasoning"] == record["label"] else f" DISAGREE (reasoning: {record['reasoning']})"
        print(f"{record['judgment']} {record['row']} {record['question']}: {record['label']} {record['confidence']:.3f} {flag}{agree}")
    return 0


def command_backfill(root, args):
    lines, rows = ledger(root)
    kinds = dc.profile_kinds(root)
    count = 0
    known = labels(root)
    if args.judgment == "J7":
        for item in known.get("J7", []):
            records = judge(root, "J7", item["id"], item["truth"], state=item.get("state"))
            for record in records:
                mark = "agree" if record["label"] == record["reasoning"] else f"DISAGREE (label: {record['reasoning']})"
                print(f"{record['row']}: {record['label']} {record['confidence']:.3f} {mark}")
            count += 1
        print(f"{count} triggers sent")
        return 0
    if args.judgment == "J2" and known.get("J2"):
        for row_id, truth in known["J2"].items():
            records = judge(root, "J2", row_id, truth)
            for record in records:
                mark = "agree" if record["label"] == record["reasoning"] else f"DISAGREE (label: {record['reasoning']})"
                print(f"{record['row']}: {record['label']} {record['confidence']:.3f} {mark}")
            count += 1
        print(f"{count} rows sent")
        return 0
    for row in rows.values():
        if not row.tagged or not row.tags:
            continue
        if args.judgment == "J1" and not (dc.kind_of(row, kinds) == "defect" and row.values("lineage")):
            continue
        if args.judgment == "J2" and dc.kind_of(row, kinds) not in ("defect", "result"):
            continue
        truth = lambda question, r=row: truth_for(args.judgment, r, question)
        records = judge(root, args.judgment, row.id, truth)
        for record in records:
            mark = "agree" if record["label"] == record["reasoning"] else f"DISAGREE (tags: {record['reasoning']})"
            print(f"{record['row']} {record['question']}: {record['label']} {record['confidence']:.3f} {mark}")
        count += 1
        if args.limit and count >= args.limit:
            break
    print(f"{count} rows sent")
    return 0


def command_tag(root, args):
    spec = specs()["judgments"]["J1"]
    records = judge(root, "J1", args.row)
    escalated = [r for r in records if r["escalate"]]
    for record in records:
        flag = "ESCALATE" if record["escalate"] else "ok"
        print(f"J1 {args.row} {record['question']}: {record['label']} {record['confidence']:.3f} {flag}")
    settled = [r for r in records if not r["escalate"]]
    if escalated:
        print(f"for the reasoning agent: {', '.join(r['question'] for r in escalated)} (below {spec['threshold']} or escalate-always)")
    keys = [f"{r['question']}:{r['label']}" for r in settled if r["label"] != "none"]
    if not keys:
        print(f"{args.row}: nothing confident to write")
        return 3 if escalated else 0
    lowest = min(r["confidence"] for r in settled)
    ledger_path = dc.profile_path(root, "Ledger", "doctrine/ledger.md")
    lines, rows, newline = dc.parse_ledger(ledger_path)
    row = rows[args.row]
    line = lines[row.index].rstrip()
    addition = f"lineage={', '.join(keys)}; judged-by=fast; confidence={lowest:.2f}" if keys else f"judged-by=fast; confidence={lowest:.2f}"
    if row.tagged and row.tags:
        if row.values("lineage"):
            print(f"{args.row} already has a lineage: {', '.join(row.values('lineage'))}; left as it is")
            return 0
        inner = line[:-1].rstrip()
        cut = inner.rfind(" | ")
        lines[row.index] = f"{inner[:cut]} | {inner[cut + 3:].strip()}; {addition} |"
    else:
        lines[row.index] = f"{line} {addition} |"
    ledger_path.write_bytes((newline.join(lines) + newline).encode("utf-8"))
    print(f"tagged {args.row}: {addition}")
    return 0


def park_groups(lines, rows):
    groups = {}
    for row in rows.values():
        if dc.state_of(row) != "parked":
            continue
        observable = dc.park_observable(lines[row.index])
        if observable:
            groups.setdefault(observable, []).append(row.id)
    return [("+".join(sorted(ids)), observable) for observable, ids in groups.items()]


def result_facts(lines, row):
    parts = cells(lines[row.index])
    return {"experiment": parts[1] if len(parts) > 1 else "", "result": parts[2] if len(parts) > 2 else ""}


def words(text):
    return set(re.findall(r"[a-z][a-z0-9-]{3,}", text.lower()))


def rejected_hypotheses(root):
    path = dc.profile_path(root, "Campaign file", "doctrine/campaign.md")
    if not path.exists():
        return []
    items, inside = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Rejected hypotheses"
            continue
        if not inside:
            continue
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif line.startswith("  ") and items:
            items[-1] += " " + line.strip()
    return items


def print_records(records, detail=None):
    for record in records:
        flag = "ESCALATE" if record["escalate"] else "ok"
        agree = ""
        if record["reasoning"]:
            agree = " agree" if record["reasoning"] == record["label"] else f" DISAGREE (reasoning: {record['reasoning']})"
        extra = f" {detail(record)}" if detail else ""
        print(f"{record['judgment']} {record['row']} {record['question']}: {record['label']} {record['confidence']:.3f}{extra} {flag}{agree}")


def command_watch(root, args):
    spec = specs()["judgments"]["J10"]
    lines, rows = ledger(root)
    row = rows.get(args.row)
    if row is None:
        raise SystemExit(f"no ledger row {args.row}")
    groups = park_groups(lines, rows)
    if not groups:
        print("no parked rows with an 'Observes:' sentence")
        return 0
    state = {"result": result_facts(lines, row)}
    known = labels(root).get("J10", {}).get(args.row, {})
    records = []
    for key, observable in groups:
        question = {
            key: {
                "type": "noul",
                "instructions": spec["instructions"].format(observable=observable),
                "criteria": {name: text.format(observable=observable) for name, text in spec["criteria"].items()},
            }
        }
        records += judge(root, "J10", args.row, lambda question: known.get(question), log=not args.no_log, state=state, questions=question)
    records.sort(key=lambda record: -float(record["probabilities"].get("noul") or 0.0))
    print_records(records, lambda record: f"p={float(record['probabilities'].get('noul') or 0.0):.2f}")
    relevant = [record["question"] for record in records if record["label"] == "relevant"]
    print(f"check these parks' triggers against {args.row}: {', '.join(relevant) if relevant else 'none'}")
    return 0


def command_dupe(root, args):
    spec = specs()["judgments"]["J11"]
    lines, rows = ledger(root)
    kinds = dc.profile_kinds(root)
    row = rows.get(args.row)
    if row is None:
        raise SystemExit(f"no ledger row {args.row}")
    if dc.kind_of(row, kinds) == "defect":
        finding = observation(lines, row)
        pool = [other for other in rows.values() if other.id != row.id and dc.kind_of(other, kinds) == "defect"]
        keys = set(row.values("lineage"))
        shared = [other for other in pool if not other.values("lineage") or keys & set(other.values("lineage"))]
        texts = {other.id: observation(lines, other) for other in (shared or pool)}
    else:
        facts = result_facts(lines, row)
        finding = f"{facts['experiment']} {facts['result']}"
        texts = {f"H-{index + 1}": text for index, text in enumerate(rejected_hypotheses(root))}
    if not texts:
        print("no earlier records to compare")
        return 0
    mine = words(finding)
    ranked = sorted(texts, key=lambda key: -len(mine & words(texts[key])))[: spec["candidates"]]
    criteria = {key: texts[key][:300] for key in ranked}
    criteria.update(spec["extra"])
    questions = {"J11": {"type": "choice", "instructions": spec["instructions"], "criteria": criteria}}
    known = labels(root).get("J11", {}).get(args.row)
    records = judge(root, "J11", args.row, known, log=not args.no_log, state={"finding": finding}, questions=questions)
    print_records(records)
    print(f"compared against {len(ranked)} of {len(texts)} earlier records")
    return 0


def command_calibrate(root, args):
    path = root / "doctrine" / "judgments.jsonl"
    since = args.since or ""
    if not path.exists():
        print("no judgments recorded")
        return 0
    groups = defaultdict(list)
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("reasoning") and record["at"] >= since and (not args.judgment or record["judgment"] == args.judgment):
            groups[record["judgment"]].append(record)
    spec_all = specs()["judgments"]
    for judgment, records in sorted(groups.items()):
        total = len(records)
        right = sum(1 for r in records if r["label"] == r["reasoning"])
        print(f"{judgment} ({spec_all[judgment]['name']}): {right}/{total} agree ({right / total:.0%}), start threshold {spec_all[judgment]['threshold']}")
        proposed = None
        for low, high in reversed(BANDS):
            band = [r for r in records if low <= r["confidence"] < high]
            if not band:
                continue
            ok = sum(1 for r in band if r["label"] == r["reasoning"])
            print(f"  confidence {low:.2f}-{min(high, 1.0):.2f}: {ok}/{len(band)} agree ({ok / len(band):.0%})")
        cumulative = []
        for low, high in reversed(BANDS):
            cumulative.extend(r for r in records if low <= r["confidence"] < high)
            ok = sum(1 for r in cumulative if r["label"] == r["reasoning"])
            if len(cumulative) >= args.minimum and ok / len(cumulative) >= args.target:
                proposed = low
        verdict = f"live at confidence >= {proposed:.2f}" if proposed is not None else "stay in shadow: not enough agreement or samples"
        print(f"  proposal (target {args.target:.0%}, at least {args.minimum} samples): {verdict}")
    return 0


def main():
    parser = argparse.ArgumentParser(prog="judge")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask")
    ask.add_argument("judgment", choices=["J1", "J2", "J7"])
    ask.add_argument("row")
    ask.add_argument("--reasoning")
    ask.add_argument("--no-log", action="store_true")
    backfill = sub.add_parser("backfill")
    backfill.add_argument("judgment", choices=["J1", "J2", "J7"])
    backfill.add_argument("--limit", type=int, default=0)
    tag = sub.add_parser("tag")
    tag.add_argument("row")
    watch = sub.add_parser("watch")
    watch.add_argument("row")
    watch.add_argument("--no-log", action="store_true")
    dupe = sub.add_parser("dupe")
    dupe.add_argument("row")
    dupe.add_argument("--no-log", action="store_true")
    calibrate = sub.add_parser("calibrate")
    calibrate.add_argument("judgment", nargs="?")
    calibrate.add_argument("--target", type=float, default=0.95)
    calibrate.add_argument("--minimum", type=int, default=20)
    calibrate.add_argument("--since", help="only calls at or after this ISO time, e.g. after a spec change")
    args = parser.parse_args()
    root = dc.find_root(args.root)
    handlers = {
        "ask": command_ask,
        "backfill": command_backfill,
        "calibrate": command_calibrate,
        "tag": command_tag,
        "watch": command_watch,
        "dupe": command_dupe,
    }
    sys.exit(handlers[args.command](root, args))


if __name__ == "__main__":
    main()
