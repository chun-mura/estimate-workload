#!/usr/bin/env python3
"""estimate プラグインの統計処理と履歴ファイル I/O。

スキルとエージェントは算術処理や `.estimate/history.jsonl` の直接編集を
行ってはならない。このスクリプトは、計算、スキーマ検証、ID生成、ロック、
バージョン処理を一元的に扱う。

契約: `estimate_calc.py <subcommand> --input <file|->` は JSON ペイロードを
読み込み、JSON の結果を標準出力へ書き出す。エラー時は
`{"error": "..."}` を標準エラー出力へ書き出し、終了コード 1 で終了する。
`update-actual` はペイロードではなくフラグを受け取る。Argparse レベルのエラー
（フラグやサブコマンドの不足・不明）はこの契約の対象外であり、Argparse が
標準エラー出力へ通常のテキストを出力して終了コード 2 で終了する。
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

SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSION = 2
# v1 レコードの 'pert' は beta-PERT (o+4m+p)/6 で計算されており、
# cmd_simulate が標本を取る三角分布とは一致しない。基準を混在させると
# キャリブレーション比率が壊れるため、v1 レコードは警告付きで除外する。
KNOWN_SCHEMA_VERSIONS = {2, 3}
CATEGORIES = {"backend-api", "frontend-ui", "db-migration", "infra", "test-only", "docs"}
DEFAULT_TRIALS = 10_000
DEFAULT_CORRELATION = 0.3
ANALYSIS_MODES = {"quality", "economy"}
ANALYSIS_AGENTS = {"spec-analyzer", "code-analyzer"}

# cmd_simulate が実装する標本抽出モデル。
DISTRIBUTION = "triangular"
DEFAULT_HOURS_PER_DAY = 8
LOW_SAMPLE_THRESHOLD = 10


class CalcError(Exception):
    """ユーザー向けの検証エラーまたは状態エラー。"""


def validate_run_context(value):
    """Validate and return the immutable context attached to v3 runs."""
    if not isinstance(value, dict):
        raise CalcError("run_context must be an object")
    required = ("comparison_key", "qa_included", "ai_view", "analysis_mode",
                "hours_per_day", "correlation", "sources", "scope",
                "exclusions", "dependencies", "assumptions")
    extra = set(value) - set(required)
    if extra:
        raise CalcError(f"run_context: unknown keys {sorted(extra)}")
    for key in required:
        if key not in value:
            raise CalcError(f"run_context requires '{key}'")
    for key in ("comparison_key", "analysis_mode", "scope"):
        if not isinstance(value[key], str) or not value[key]:
            raise CalcError(f"run_context.{key} must be a non-empty string")
    for key in ("qa_included", "ai_view"):
        if not isinstance(value[key], bool):
            raise CalcError(f"run_context.{key} must be a boolean")
    for key in ("hours_per_day", "correlation"):
        if not _is_number(value[key]) or value[key] <= 0 or (key == "correlation" and value[key] > 1):
            raise CalcError(f"run_context.{key} must be a finite positive number")
    for key in ("sources", "exclusions", "dependencies", "assumptions"):
        if not isinstance(value[key], list) or not all(isinstance(x, str) and x for x in value[key]):
            raise CalcError(f"run_context.{key} must be a list of strings")
    return dict(value)


def percentile(values, q):
    """値の線形補間パーセンタイル。q は [0, 100]。"""
    if not values:
        raise CalcError("percentile of empty list")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def triangular_mean(o, m, p):
    """Triangular(o, m, p) の平均値。cmd_simulate が標本を取る分布。

    履歴ではスキーマ安定性のため 'pert' フィールドに保存する。キャリブレーションは
    実績をこの値で割るため、シミュレーションモデルとの整合性を保つ必要がある。
    """
    return round((o + m + p) / 3.0, 2)


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_three_point(task, label):
    for key in ("o", "m", "p"):
        v = task.get(key)
        if not _is_number(v) or v < 0:
            raise CalcError(f"{label}: '{key}' must be a non-negative finite number")
    if not task["o"] <= task["m"] <= task["p"]:
        raise CalcError(f"{label}: requires o <= m <= p")


def triangular_inv_cdf(u, o, m, p):
    """u が [0, 1] のときの Triangular(o, m, p) の逆累積分布関数。"""
    if o == p:
        return o
    fc = (m - o) / (p - o)
    if u < fc:
        return o + math.sqrt(u * (p - o) * (m - o))
    return p - math.sqrt((1 - u) * (p - o) * (p - m))


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
    correlation = payload.get("correlation", DEFAULT_CORRELATION)
    if not _is_number(correlation) or not 0 <= correlation <= 1:
        raise CalcError("simulate: 'correlation' must be a finite number in [0, 1]")
    hours_per_day = payload.get("hours_per_day", DEFAULT_HOURS_PER_DAY)
    if not _is_number(hours_per_day) or hours_per_day <= 0:
        raise CalcError("simulate: 'hours_per_day' must be a positive finite number")

    seed = payload.get("seed")
    if seed is None:
        # seed がない実行は再現不能になるため、ここで seed を決定する。呼び出し元は
        # これを保存し、同一の合計値を再現できる。IEEE-754 倍精度数で数値を扱う
        # JSON リーダーでも保持されるよう 2**53 未満にする。丸められた seed では
        # 異なる実行を再現してしまう。
        seed = random.randrange(2 ** 53)
    elif not isinstance(seed, int) or isinstance(seed, bool):
        raise CalcError("simulate: 'seed' must be an integer")
    rng = random.Random(seed)
    common_weight = math.sqrt(correlation)
    individual_weight = math.sqrt(1 - correlation)
    totals = []
    for _ in range(trials):
        common = rng.gauss(0, 1)
        total = 0.0
        for t in scaled:
            if t["o"] == t["p"]:
                total += t["o"]
            else:
                z = common_weight * common + individual_weight * rng.gauss(0, 1)
                u = 0.5 * (1 + math.erf(z / math.sqrt(2)))
                total += triangular_inv_cdf(u, t["o"], t["m"], t["p"])
        totals.append(total)
    p50 = percentile(totals, 50)
    p80 = percentile(totals, 80)
    result = {
        "tasks": [
            {"name": t["name"], "pert": triangular_mean(t["o"], t["m"], t["p"])}
            for t in scaled
        ],
        "total": {
            "mean": round(statistics.fmean(totals), 2),
            "p50": round(p50, 2),
            "p80": round(p80, 2),
            "p50_days": round(p50 / hours_per_day, 2),
            "p80_days": round(p80 / hours_per_day, 2),
            "min": round(min(totals), 2),
            "max": round(max(totals), 2),
        },
        "trials": trials,
        "correlation": correlation,
        "hours_per_day": hours_per_day,
        "distribution": DISTRIBUTION,
        "seed": seed,
    }
    return result


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
    if sv == 3:
        try:
            validate_run_context(rec.get("run_context"))
        except CalcError as exc:
            return str(exc)
        if not isinstance(rec.get("run_summary"), dict):
            return "v3 record requires run_summary"
    return None


def read_history(path):
    """(有効なレコード, 警告) を返す。ファイルがなければ履歴はまだない。"""
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


def _required_string(payload, key, command):
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise CalcError(f"{command}: '{key}' must be a non-empty string")
    return value


def _validated_analysis(payload, command):
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        raise CalcError(f"{command}: 'analysis' must be an object")
    mode = analysis.get("mode")
    agents = analysis.get("agents")
    if not isinstance(mode, str) or mode not in ANALYSIS_MODES:
        raise CalcError(
            f"{command}: 'analysis.mode' must be one of {sorted(ANALYSIS_MODES)}"
        )
    if not isinstance(agents, list) or not agents:
        raise CalcError(f"{command}: 'analysis.agents' must be a non-empty list")
    if any(
        not isinstance(agent, str) or agent not in ANALYSIS_AGENTS
        for agent in agents
    ):
        raise CalcError(
            f"{command}: 'analysis.agents' must contain only "
            f"{sorted(ANALYSIS_AGENTS)}"
        )
    if len(set(agents)) != len(agents):
        raise CalcError(f"{command}: 'analysis.agents' must not contain duplicates")
    if mode == "economy" and agents != ["spec-analyzer"]:
        raise CalcError(
            f"{command}: economy analysis requires ['spec-analyzer']"
        )
    return {"mode": mode, "agents": agents}


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
    record_schema = payload.get("schema_version", LEGACY_SCHEMA_VERSION)
    if record_schema not in (LEGACY_SCHEMA_VERSION, SCHEMA_VERSION):
        raise CalcError("append-history: unsupported schema_version")
    context = None
    summary = None
    if record_schema == SCHEMA_VERSION:
        context = validate_run_context(payload.get("run_context"))
        summary = payload.get("run_summary")
        if not isinstance(summary, dict):
            raise CalcError("append-history: run_summary must be an object")
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

    lock_timeout = payload.get("lock_timeout", 5.0)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    lock = _acquire_lock(path, lock_timeout)
    try:
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
                "schema_version": record_schema,
                "run_id": run_id,
                "id": f"{run_id}-{i:02d}",
                "date": now.strftime("%Y-%m-%d"),
                "task": t["task"],
                "category": t["category"],
                "tags": t.get("tags", []),
                "o": t["o"],
                "m": t["m"],
                "p": t["p"],
                "pert": triangular_mean(t["o"], t["m"], t["p"]),
                "actual": None,
                "ai_assisted": None,
                "status": "estimated",
            }
            if record_schema == SCHEMA_VERSION:
                rec["run_context"] = context
                rec["run_summary"] = summary
            lines.append(json.dumps(rec, ensure_ascii=False))
        data = ("\n".join(lines) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        return {"run_id": run_id, "appended": len(lines)}
    finally:
        os.remove(lock)


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


def cmd_reference_class(payload):
    path = payload.get("history_path")
    if not isinstance(path, str) or not path:
        raise CalcError("reference-class: 'history_path' is required")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("reference-class: 'tasks' must be a non-empty list")
    min_records = payload.get("min_records", 5)
    max_anchors = payload.get("max_anchors", 3)
    for key, value in (("min_records", min_records), ("max_anchors", max_anchors)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise CalcError(f"reference-class: '{key}' must be a positive integer")
    records, warnings = read_history(path)
    done = [
        r for r in records
        if r["status"] == "done" and _is_number(r.get("actual"))
        and r["actual"] > 0 and r["pert"] > 0
    ]
    results = []
    for i, t in enumerate(tasks):
        if t.get("category") not in CATEGORIES:
            raise CalcError(
                f"reference-class: tasks[{i}] category {t.get('category')!r} unknown"
            )
        tags = set(t.get("tags") or [])
        same_cat = [r for r in done if r["category"] == t["category"]]
        ranked = sorted(
            same_cat,
            key=lambda r: (len(tags & set(r["tags"])), r["date"]),
            reverse=True,
        )
        anchors = [
            {k: r.get(k) for k in ("task", "pert", "actual", "ai_assisted",
                                    "tags")}
            for r in ranked[:max_anchors]
        ]
        entry = {"name": t.get("name", ""), "anchors": anchors}
        # アンカーが示す母集団と同じデータから補正する。タグが重なるレコードを優先し、
        # タグ一致の母集団が補正に小さすぎる場合にだけ、カテゴリ全体へフォールバックする。
        tag_matched = [r for r in same_cat if tags & set(r["tags"])] if tags else []
        if len(tag_matched) >= min_records:
            pool, basis = tag_matched, "category_and_tags"
        else:
            pool, basis = same_cat, "category"
        ratios = [r["actual"] / r["pert"] for r in pool]
        if len(ratios) < min_records:
            entry["correction"] = {"skipped": "insufficient_data", "count": len(ratios)}
        else:
            r50 = percentile(ratios, 50)
            r80 = percentile(ratios, 80)
            correction = {
                "count": len(ratios),
                "basis": basis,
                "ratio_p50": round(r50, 2),
                "ratio_p80": round(r80, 2),
            }
            if len(ratios) < LOW_SAMPLE_THRESHOLD:
                correction["low_sample"] = True
            if _is_number(t.get("m")):
                corrected_m = t["m"] * r50
                correction["corrected_m"] = round(corrected_m, 2)
                if _is_number(t.get("o")):
                    correction["corrected_o"] = round(
                        min(t["o"] * r50, corrected_m), 2
                    )
            if _is_number(t.get("p")):
                correction["corrected_p"] = round(t["p"] * r80, 2)
            entry["correction"] = correction
        results.append(entry)
    return {"tasks": results, "warnings": warnings}


def cmd_calibration(payload):
    path = payload.get("history_path")
    if not isinstance(path, str) or not path:
        raise CalcError("calibration: 'history_path' is required")
    records, warnings = read_history(path)
    done = [
        r for r in records
        if r["status"] == "done" and _is_number(r.get("actual"))
        and r["actual"] > 0 and r["pert"] > 0
    ]
    if not done:
        return {"skipped": "no_completed_records", "warnings": warnings}
    ratios = [r["actual"] / r["pert"] for r in done]
    p50 = percentile(ratios, 50)
    if p50 > 1.05:
        bias = "underestimating"
    elif p50 < 0.95:
        bias = "overestimating"
    else:
        bias = "well_calibrated"
    by_cat = {}
    for r in done:
        by_cat.setdefault(r["category"], []).append(r["actual"] / r["pert"])
    ai_factors = {}
    for cat in by_cat:
        ai = [r["actual"] / r["pert"] for r in done
              if r["category"] == cat and r.get("ai_assisted") is True]
        human = [r["actual"] / r["pert"] for r in done
                 if r["category"] == cat and r.get("ai_assisted") is False]
        if len(ai) >= 3 and len(human) >= 3:
            ai_factors[cat] = {
                "factor": round(percentile(ai, 50) / percentile(human, 50), 2),
                "ai_count": len(ai),
                "human_count": len(human),
            }
            if min(len(ai), len(human)) < LOW_SAMPLE_THRESHOLD:
                ai_factors[cat]["low_sample"] = True
    result = {
        "count": len(done),
        "ratio_p50": round(p50, 2),
        "ratio_mean": round(statistics.fmean(ratios), 2),
        "bias": bias,
        "by_category": {
            c: {"count": len(v), "ratio_p50": round(percentile(v, 50), 2)}
            for c, v in sorted(by_cat.items())
        },
        "ai_assistance_factors": ai_factors,
        "warnings": warnings,
    }
    if len(done) < LOW_SAMPLE_THRESHOLD:
        result["low_sample"] = True
    return result


def cmd_pipeline(payload):
    """WBS後の全処理を1回で実行する。

    参照クラス補正、従来型・AI支援のシミュレーション、履歴への追記を行う。

    純粋な計算を先に実行するため、検証またはシミュレーションが失敗してもディスクへ
    変更は残らない。履歴だけが永続化される出力である。
    """
    history_path = _required_string(payload, "history_path", "pipeline")
    _required_string(payload, "slug", "pipeline")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("pipeline: 'tasks' must be a non-empty list")
    ai_view = payload.get("ai_view", True)
    if not isinstance(ai_view, bool):
        raise CalcError("pipeline: 'ai_view' must be a boolean")
    analysis = _validated_analysis(payload, "pipeline")
    run_context = None
    if "run_context" in payload:
        run_context = validate_run_context(payload.get("run_context"))
    for i, t in enumerate(tasks):
        label = f"pipeline: tasks[{i}]"
        if not isinstance(t, dict) or not isinstance(t.get("task"), str) \
                or not t["task"]:
            raise CalcError(f"{label}: 'task' must be a non-empty string")
        if t.get("category") not in CATEGORIES:
            raise CalcError(
                f"{label}: category {t.get('category')!r} not in "
                f"{sorted(CATEGORIES)}"
            )
        validate_three_point(t, label)
        if ai_view:
            factor = t.get("default_factor")
            if not _is_number(factor) or factor <= 0:
                raise CalcError(
                    f"{label}: 'default_factor' must be a positive number "
                    "when 'ai_view' is true"
                )

    ref = cmd_reference_class({
        "history_path": history_path,
        "tasks": [
            {"name": t["task"], "category": t.get("category"),
             "tags": t.get("tags", []), "o": t["o"], "m": t["m"], "p": t["p"]}
            for t in tasks
        ],
    })
    final = []
    for t, entry in zip(tasks, ref["tasks"]):
        corr = entry["correction"]
        final.append({
            "task": t["task"], "category": t["category"],
            "tags": t.get("tags", []),
            "o": corr.get("corrected_o", t["o"]),
            "m": corr.get("corrected_m", t["m"]),
            "p": corr.get("corrected_p", t["p"]),
            "correction": {
                k: v for k, v in corr.items() if not k.startswith("corrected_")
            },
        })

    sim_base = {
        key: payload[key]
        for key in ("correlation", "hours_per_day", "trials", "seed")
        if key in payload
    }
    traditional = cmd_simulate({**sim_base, "tasks": [
        {"name": t["task"], "o": t["o"], "m": t["m"], "p": t["p"]}
        for t in final
    ]})

    ai_assisted = None
    factors = []
    if ai_view:
        calibration = cmd_calibration({"history_path": history_path})
        learned = calibration.get("ai_assistance_factors") or {}
        ai_tasks = []
        for t, ft in zip(tasks, final):
            entry = learned.get(ft["category"])
            if entry:
                info = {"factor": entry["factor"], "source": "learned"}
                if entry.get("low_sample"):
                    info["low_sample"] = True
            else:
                info = {"factor": t["default_factor"], "source": "default"}
            factors.append(info)
            ai_tasks.append({"name": ft["task"], "o": ft["o"], "m": ft["m"],
                             "p": ft["p"], "factor": info["factor"]})
        ai_assisted = cmd_simulate({**sim_base, "tasks": ai_tasks})

    append_payload = {
        "history_path": history_path, "slug": payload["slug"],
        "tasks": [
            {k: t[k] for k in ("task", "category", "tags", "o", "m", "p")}
            for t in final
        ],
    }
    if "lock_timeout" in payload:
        append_payload["lock_timeout"] = payload["lock_timeout"]
    run_summary = {
        "traditional": traditional["total"],
        "simulation": {"distribution": traditional["distribution"],
                        "trials": traditional["trials"],
                        "correlation": traditional["correlation"],
                        "hours_per_day": traditional["hours_per_day"],
                        "traditional_seed": traditional["seed"],
                        "ai_assisted_seed": ai_assisted["seed"] if ai_assisted else None},
    }
    if run_context is not None:
        append_payload.update({"schema_version": SCHEMA_VERSION,
                               "run_context": run_context,
                               "run_summary": run_summary})
    run_id = cmd_append_history(append_payload)["run_id"]

    # レポートへ再現条件を記録できるよう、呼び出し元へ返す。
    simulation = {
        "distribution": traditional["distribution"],
        "trials": traditional["trials"],
        "correlation": traditional["correlation"],
        "hours_per_day": traditional["hours_per_day"],
        # 各ビューは独立したストリームから標本を取るため、それぞれ固有の seed を持つ。
        "traditional_seed": traditional["seed"],
        "ai_assisted_seed": ai_assisted["seed"] if ai_assisted else None,
    }
    out_tasks = []
    for i, t in enumerate(final):
        out = {
            "id": f"{run_id}-{i + 1:02d}",
            "task": t["task"], "category": t["category"],
            "o": t["o"], "m": t["m"], "p": t["p"],
            "pert": traditional["tasks"][i]["pert"],
            "correction": t["correction"],
        }
        if ai_view:
            out["ai_factor"] = factors[i]
        out_tasks.append(out)
    result = {
        "run_id": run_id,
        "tasks": out_tasks,
        "traditional": traditional["total"],
        "ai_assisted": ai_assisted["total"] if ai_assisted else None,
        "analysis": analysis,
        "trials": traditional["trials"],
        "correlation": traditional["correlation"],
        "hours_per_day": traditional["hours_per_day"],
        "simulation": simulation,
        "warnings": ref["warnings"],
    }
    if run_context is not None:
        result.update({"run_context": run_context, "run_summary": run_summary})
    return result


def cmd_distribute(payload):
    total = payload.get("total")
    if not _is_number(total) or total <= 0:
        raise CalcError("distribute: 'total' must be a positive number")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CalcError("distribute: 'tasks' must be a non-empty list")
    for i, t in enumerate(tasks):
        if not isinstance(t.get("id"), str) or not t["id"]:
            raise CalcError(f"distribute: tasks[{i}] needs a non-empty 'id'")
        if not _is_number(t.get("pert")) or t["pert"] <= 0:
            raise CalcError(f"distribute: tasks[{i}] 'pert' must be > 0")
    pert_sum = sum(t["pert"] for t in tasks)
    total_units = round(total * 10)
    raws = [total_units * t["pert"] / pert_sum for t in tasks]
    bases = [int(r) for r in raws]
    remainders = [r - b for r, b in zip(raws, bases)]
    leftover = total_units - sum(bases)
    order = sorted(range(len(tasks)), key=lambda i: remainders[i], reverse=True)
    for i in order[:leftover]:
        bases[i] += 1
    shares = [
        {"id": t["id"], "actual": units / 10.0}
        for t, units in zip(tasks, bases)
    ]
    return {"shares": shares}


def _load_payload(spec):
    if spec == "-":
        return json.load(sys.stdin)
    with open(spec, encoding="utf-8") as fh:
        return json.load(fh)


PAYLOAD_COMMANDS = {
    "simulate": cmd_simulate,
    "append-history": cmd_append_history,
    "reference-class": cmd_reference_class,
    "calibration": cmd_calibration,
    "distribute": cmd_distribute,
    "pipeline": cmd_pipeline,
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
    except Exception as exc:
        json.dump({"error": f"unexpected: {type(exc).__name__}: {exc}"}, sys.stderr)
        sys.stderr.write("\n")
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
