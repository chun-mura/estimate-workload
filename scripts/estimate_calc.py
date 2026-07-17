#!/usr/bin/env python3
"""All statistics and history-file I/O for the estimate plugin.

Skills and agents must never do arithmetic or edit .estimate/history.jsonl
directly; this script is the single choke point for math, schema
validation, ID generation, locking, and version handling.

Contract: `estimate_calc.py <subcommand> --input <file|->` reads a JSON
payload, writes a JSON result to stdout, and on error writes
{"error": "..."} to stderr and exits 1. `update-actual` takes flags
instead of a payload.
"""
import argparse
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time
from datetime import datetime

SCHEMA_VERSION = 1
KNOWN_SCHEMA_VERSIONS = {1}
CATEGORIES = {"backend-api", "frontend-ui", "db-migration", "infra", "test-only", "docs"}
DEFAULT_TRIALS = 10_000


class CalcError(Exception):
    """User-facing validation or state error."""


def percentile(values, q):
    """Linear-interpolated percentile of values, q in [0, 100]."""
    if not values:
        raise CalcError("percentile of empty list")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def pert_mean(o, m, p):
    return round((o + 4 * m + p) / 6.0, 2)


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_three_point(task, label):
    for key in ("o", "m", "p"):
        v = task.get(key)
        if not _is_number(v) or v < 0:
            raise CalcError(f"{label}: '{key}' must be a non-negative finite number")
    if not task["o"] <= task["m"] <= task["p"]:
        raise CalcError(f"{label}: requires o <= m <= p")


def cmd_simulate(payload):
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("simulate: 'tasks' must be a non-empty list")
    scaled = []
    for i, t in enumerate(tasks):
        validate_three_point(t, f"tasks[{i}]")
        factor = t.get("factor", 1)
        if not _is_number(factor) or factor <= 0:
            raise CalcError(f"tasks[{i}]: 'factor' must be a positive number")
        scaled.append(
            {"name": t.get("name", ""), "o": t["o"] * factor,
             "m": t["m"] * factor, "p": t["p"] * factor}
        )
    trials = payload.get("trials", DEFAULT_TRIALS)
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise CalcError("simulate: 'trials' must be a positive integer")
    rng = random.Random(payload.get("seed"))
    totals = []
    for _ in range(trials):
        total = 0.0
        for t in scaled:
            if t["o"] == t["p"]:
                total += t["o"]
            else:
                total += rng.triangular(t["o"], t["p"], t["m"])
        totals.append(total)
    return {
        "tasks": [
            {"name": t["name"], "pert": pert_mean(t["o"], t["m"], t["p"])}
            for t in scaled
        ],
        "total": {
            "mean": round(statistics.fmean(totals), 2),
            "p50": round(percentile(totals, 50), 2),
            "p80": round(percentile(totals, 80), 2),
            "min": round(min(totals), 2),
            "max": round(max(totals), 2),
        },
        "trials": trials,
    }


def schema_error(rec):
    if not isinstance(rec, dict):
        return "record is not an object"
    sv = rec.get("schema_version")
    if sv not in KNOWN_SCHEMA_VERSIONS:
        return f"unknown schema_version: {sv!r}"
    for key in ("run_id", "id", "date", "task"):
        if not isinstance(rec.get(key), str) or not rec[key]:
            return f"'{key}' must be a non-empty string"
    if rec.get("category") not in CATEGORIES:
        return f"unknown category: {rec.get('category')!r}"
    tags = rec.get("tags")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        return "'tags' must be a list of strings"
    try:
        validate_three_point(rec, "record")
    except CalcError as exc:
        return str(exc)
    if not _is_number(rec.get("pert")):
        return "'pert' must be a number"
    actual = rec.get("actual")
    if actual is not None and (not _is_number(actual) or actual <= 0):
        return "'actual' must be null or a positive number"
    ai = rec.get("ai_assisted")
    if ai is not None and not isinstance(ai, bool):
        return "'ai_assisted' must be null or a boolean"
    if rec.get("status") not in ("estimated", "done"):
        return f"unknown status: {rec.get('status')!r}"
    return None


def read_history(path):
    """Return (valid_records, warnings); missing file means no history yet."""
    records, warnings = [], []
    if not os.path.exists(path):
        return records, warnings
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(
                    {"line": lineno, "kind": "parse_error", "detail": str(exc)}
                )
                continue
            err = schema_error(rec)
            if err:
                warnings.append(
                    {"line": lineno, "kind": "schema_violation", "detail": err}
                )
                continue
            records.append(rec)
    return records, warnings


def _existing_run_ids(path):
    run_ids = set()
    if not os.path.exists(path):
        return run_ids
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("run_id"), str):
                run_ids.add(rec["run_id"])
    return run_ids


def cmd_append_history(payload):
    path = payload.get("history_path")
    if not isinstance(path, str) or not path:
        raise CalcError("append-history: 'history_path' is required")
    slug = payload.get("slug")
    if not isinstance(slug, str) or not slug or not all(
        c.isalnum() or c == "-" for c in slug.lower()
    ):
        raise CalcError("append-history: 'slug' must be alphanumeric/hyphens")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("append-history: 'tasks' must be a non-empty list")
    for i, t in enumerate(tasks):
        label = f"tasks[{i}]"
        if not isinstance(t.get("task"), str) or not t["task"]:
            raise CalcError(f"{label}: 'task' must be a non-empty string")
        if t.get("category") not in CATEGORIES:
            raise CalcError(
                f"{label}: category {t.get('category')!r} not in {sorted(CATEGORIES)}"
            )
        tags = t.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
            raise CalcError(f"{label}: 'tags' must be a list of strings")
        validate_three_point(t, label)

    now = datetime.now()
    base = now.strftime("%Y%m%dT%H%M%S") + "-" + slug.lower()
    existing = _existing_run_ids(path)
    run_id, n = base, 2
    while run_id in existing:
        run_id = f"{base}-{n}"
        n += 1

    lines = []
    for i, t in enumerate(tasks, 1):
        rec = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "id": f"{run_id}-{i:02d}",
            "date": now.strftime("%Y-%m-%d"),
            "task": t["task"],
            "category": t["category"],
            "tags": t.get("tags", []),
            "o": t["o"],
            "m": t["m"],
            "p": t["p"],
            "pert": pert_mean(t["o"], t["m"], t["p"]),
            "actual": None,
            "ai_assisted": None,
            "status": "estimated",
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = ("\n".join(lines) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return {"run_id": run_id, "appended": len(lines)}


def _acquire_lock(path, timeout):
    lock = path + ".lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return lock
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise CalcError(
                    f"could not acquire {lock}; is another update running? "
                    "Remove the file if it is stale."
                )
            time.sleep(0.1)


def cmd_update_actual(history_path, task_id, actual, ai_assisted, lock_timeout=5.0):
    if not _is_number(actual) or actual <= 0:
        raise CalcError("update-actual: --actual must be a positive number of hours")
    if not os.path.exists(history_path):
        raise CalcError(f"update-actual: no history file at {history_path}")
    lock = _acquire_lock(history_path, lock_timeout)
    try:
        with open(history_path, encoding="utf-8") as fh:
            raw = fh.readlines()
        out_lines, updated = [], None
        for line in raw:
            rec = None
            stripped = line.strip()
            if stripped:
                try:
                    rec = json.loads(stripped)
                except json.JSONDecodeError:
                    rec = None
            if isinstance(rec, dict) and rec.get("id") == task_id:
                rec["actual"] = actual
                rec["ai_assisted"] = bool(ai_assisted)
                rec["status"] = "done"
                out_lines.append(json.dumps(rec, ensure_ascii=False) + "\n")
                updated = rec
            else:
                out_lines.append(line)
        if updated is None:
            raise CalcError(f"update-actual: no record with id {task_id!r}")
        dir_ = os.path.dirname(os.path.abspath(history_path))
        fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".history-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.writelines(out_lines)
            os.replace(tmp, history_path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        return {"updated": updated}
    finally:
        os.remove(lock)


def _load_payload(spec):
    if spec == "-":
        return json.load(sys.stdin)
    with open(spec, encoding="utf-8") as fh:
        return json.load(fh)


PAYLOAD_COMMANDS = {
    "simulate": cmd_simulate,
    "append-history": cmd_append_history,
}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="estimate_calc")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in PAYLOAD_COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("--input", default="-", help="JSON payload file, or - for stdin")
    p = sub.add_parser("update-actual")
    p.add_argument("--history-path", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--actual", type=float, required=True)
    p.add_argument("--ai-assisted", choices=["true", "false"], required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "update-actual":
            result = cmd_update_actual(
                args.history_path, args.id, args.actual, args.ai_assisted == "true"
            )
        else:
            result = PAYLOAD_COMMANDS[args.cmd](_load_payload(args.input))
    except CalcError as exc:
        json.dump({"error": str(exc)}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    except json.JSONDecodeError as exc:
        json.dump({"error": f"invalid JSON payload: {exc}"}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
