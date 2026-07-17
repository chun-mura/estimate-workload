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


def _load_payload(spec):
    if spec == "-":
        return json.load(sys.stdin)
    with open(spec, encoding="utf-8") as fh:
        return json.load(fh)


PAYLOAD_COMMANDS = {
    "simulate": cmd_simulate,
}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="estimate_calc")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in PAYLOAD_COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("--input", default="-", help="JSON payload file, or - for stdin")
    args = parser.parse_args(argv)
    try:
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
