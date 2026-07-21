import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import estimate_calc as ec


class TestPercentile(unittest.TestCase):
    def test_median_odd(self):
        self.assertEqual(ec.percentile([3, 1, 2], 50), 2)

    def test_interpolates(self):
        self.assertEqual(ec.percentile([1, 2, 3, 4], 50), 2.5)

    def test_p80(self):
        self.assertAlmostEqual(ec.percentile([1, 2, 3, 4, 5], 80), 4.2)

    def test_empty_raises(self):
        with self.assertRaises(ec.CalcError):
            ec.percentile([], 50)


class TestTriangularInvCdf(unittest.TestCase):
    def test_endpoints_and_mode(self):
        self.assertEqual(ec.triangular_inv_cdf(0.0, 2, 5, 10), 2)
        self.assertEqual(ec.triangular_inv_cdf(1.0, 2, 5, 10), 10)
        fc = (5 - 2) / (10 - 2)
        self.assertAlmostEqual(ec.triangular_inv_cdf(fc, 2, 5, 10), 5)

    def test_degenerate_distribution_is_constant(self):
        self.assertEqual(ec.triangular_inv_cdf(0.37, 5, 5, 5), 5)


class TestSimulate(unittest.TestCase):
    def payload(self, **over):
        base = {
            "tasks": [
                {"name": "a", "o": 4, "m": 8, "p": 16},
                {"name": "b", "o": 2, "m": 3, "p": 10},
            ],
            "trials": 2000,
            "seed": 42,
        }
        base.update(over)
        return base

    def test_task_means_match_sampled_triangular_distribution(self):
        out = ec.cmd_simulate(self.payload())
        self.assertEqual(out["tasks"][0]["pert"], 9.33)  # (4+8+16)/3
        self.assertEqual(out["tasks"][1]["pert"], 5.0)   # (2+3+10)/3

    def test_task_mean_approximates_simulated_mean(self):
        # 'pert' の点推定値とモンテカルロの合計値は同じ分布に基づく必要がある。
        # 異なる分布では、構造上キャリブレーション比率がずれてしまう。
        out = ec.cmd_simulate({
            "tasks": [{"name": "x", "o": 2, "m": 4, "p": 20}],
            "trials": 50_000, "seed": 42, "correlation": 0,
        })
        self.assertAlmostEqual(out["tasks"][0]["pert"], out["total"]["mean"], delta=0.1)

    def test_seed_deterministic(self):
        a = ec.cmd_simulate(self.payload())
        b = ec.cmd_simulate(self.payload())
        self.assertEqual(a["total"], b["total"])

    def test_reports_the_model_it_sampled(self):
        out = ec.cmd_simulate(self.payload())
        self.assertEqual(out["distribution"], "triangular")

    def test_echoes_the_caller_supplied_seed(self):
        self.assertEqual(ec.cmd_simulate(self.payload(seed=42))["seed"], 42)

    def test_generates_and_reports_a_seed_when_none_given(self):
        # これがなければ seed のない実行は再現不能であり、報告した合計値を
        # サマリだけから再生成できない。
        payload = self.payload()
        del payload["seed"]
        out = ec.cmd_simulate(payload)
        self.assertIsInstance(out["seed"], int)
        replay = ec.cmd_simulate({**payload, "seed": out["seed"]})
        self.assertEqual(replay["total"], out["total"])

    def test_rejects_non_integer_seed(self):
        for bad in ("42", True, 42.0, [42]):
            with self.subTest(seed=bad), self.assertRaises(ec.CalcError):
                ec.cmd_simulate(self.payload(seed=bad))

    def test_seed_zero_is_used_not_treated_as_missing(self):
        # 0 は偽値である。真偽値判定では実行を黙って再 seed 化してしまう。
        out = ec.cmd_simulate(self.payload(seed=0))
        self.assertEqual(out["seed"], 0)
        self.assertEqual(out["total"], ec.cmd_simulate(self.payload(seed=0))["total"])

    def test_generated_seed_survives_json_round_trip(self):
        # 実行サマリは機械可読として提供する。2**53 より大きい seed は IEEE-754
        # 倍精度数を用いる JSON リーダーで精度を失い、記録した seed から別の実行を
        # 再現してしまう。
        payload = self.payload()
        del payload["seed"]
        for _ in range(200):
            seed = ec.cmd_simulate(payload)["seed"]
            self.assertLess(seed, 2 ** 53)
            self.assertEqual(json.loads(json.dumps(seed)), seed)

    def test_percentile_ordering_and_bounds(self):
        t = ec.cmd_simulate(self.payload())["total"]
        self.assertLessEqual(t["p50"], t["p80"])
        self.assertGreaterEqual(t["min"], 4 + 2)
        self.assertLessEqual(t["max"], 16 + 10)

    def test_degenerate_point_estimate(self):
        out = ec.cmd_simulate(
            {"tasks": [{"name": "x", "o": 5, "m": 5, "p": 5}], "trials": 10, "seed": 1}
        )
        self.assertEqual(out["total"]["p50"], 5)
        self.assertEqual(out["total"]["p80"], 5)

    def test_rejects_o_greater_than_m(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate({"tasks": [{"name": "x", "o": 9, "m": 8, "p": 16}]})

    def test_rejects_bool_and_negative(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate({"tasks": [{"name": "x", "o": True, "m": 8, "p": 16}]})
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate({"tasks": [{"name": "x", "o": -1, "m": 8, "p": 16}]})

    def test_rejects_empty_tasks(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate({"tasks": []})

    def test_factor_scales_task(self):
        out = ec.cmd_simulate(
            {"tasks": [{"name": "x", "o": 4, "m": 8, "p": 16, "factor": 0.5}],
             "trials": 200, "seed": 7}
        )
        self.assertEqual(out["tasks"][0]["pert"], 4.67)
        self.assertLessEqual(out["total"]["max"], 8)

    def test_rejects_bad_factor(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate(
                {"tasks": [{"name": "x", "o": 4, "m": 8, "p": 16, "factor": 0}]}
            )

    def test_person_days_use_default_hours_per_day(self):
        out = ec.cmd_simulate(self.payload())
        self.assertEqual(out["hours_per_day"], 8)
        t = out["total"]
        self.assertAlmostEqual(t["p50_days"], t["p50"] / 8, delta=0.01)
        self.assertAlmostEqual(t["p80_days"], t["p80"] / 8, delta=0.01)

    def test_person_days_honor_hours_per_day_override(self):
        out = ec.cmd_simulate(self.payload(hours_per_day=6))
        self.assertEqual(out["hours_per_day"], 6)
        t = out["total"]
        self.assertAlmostEqual(t["p80_days"], t["p80"] / 6, delta=0.01)

    def test_rejects_invalid_hours_per_day(self):
        for value in (0, -8, float("nan"), True, "8"):
            with self.subTest(value=value), self.assertRaises(ec.CalcError):
                ec.cmd_simulate(self.payload(hours_per_day=value))

    def test_default_and_explicit_correlation_are_reported(self):
        self.assertEqual(ec.cmd_simulate(self.payload())["correlation"], 0.3)
        self.assertEqual(ec.cmd_simulate(self.payload(correlation=0.7))["correlation"], 0.7)

    def test_rejects_invalid_correlation(self):
        for value in (-0.01, 1.01, float("nan"), float("inf"), True, "0.3"):
            with self.subTest(value=value), self.assertRaises(ec.CalcError):
                ec.cmd_simulate(self.payload(correlation=value))

    def test_mean_is_approximately_invariant_to_correlation(self):
        independent = ec.cmd_simulate(self.payload(trials=50_000, correlation=0))["total"]
        correlated = ec.cmd_simulate(self.payload(trials=50_000, correlation=0.9))["total"]
        self.assertAlmostEqual(independent["mean"], correlated["mean"], delta=0.12)

    def test_high_correlation_raises_multi_task_p80(self):
        independent = ec.cmd_simulate(self.payload(trials=50_000, correlation=0))["total"]
        correlated = ec.cmd_simulate(self.payload(trials=50_000, correlation=0.9))["total"]
        self.assertGreater(correlated["p80"], independent["p80"])

    def test_single_task_marginal_is_approximately_invariant(self):
        base = {"tasks": [{"name": "x", "o": 2, "m": 5, "p": 12}], "trials": 50_000, "seed": 42}
        independent = ec.cmd_simulate({**base, "correlation": 0})["total"]
        correlated = ec.cmd_simulate({**base, "correlation": 0.9})["total"]
        self.assertAlmostEqual(independent["mean"], correlated["mean"], delta=0.08)
        self.assertAlmostEqual(independent["p80"], correlated["p80"], delta=0.08)

    def test_degenerate_task_is_unaffected_by_correlation(self):
        payload = {"tasks": [{"name": "x", "o": 5, "m": 5, "p": 5}], "trials": 20, "seed": 1}
        independent = ec.cmd_simulate({**payload, "correlation": 0})["total"]
        correlated = ec.cmd_simulate({**payload, "correlation": 1})["total"]
        self.assertEqual(independent, correlated)


class HistoryBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, ".estimate", "history.jsonl")
        self.addCleanup(self.dir.cleanup)

    def append(self, slug="feat", tasks=None):
        tasks = tasks or [
            {"task": "Add endpoint", "category": "backend-api", "tags": ["auth"],
             "o": 4, "m": 8, "p": 16},
        ]
        return ec.cmd_append_history(
            {"history_path": self.path, "slug": slug, "tasks": tasks}
        )

    def raw_lines(self):
        with open(self.path, encoding="utf-8") as fh:
            return [l for l in fh.read().splitlines() if l.strip()]


class TestAppendHistory(HistoryBase):
    def test_appends_stamped_records(self):
        out = self.append()
        self.assertEqual(out["appended"], 1)
        rec = json.loads(self.raw_lines()[0])
        self.assertEqual(rec["schema_version"], 2)
        self.assertEqual(rec["run_id"], out["run_id"])
        self.assertEqual(rec["id"], out["run_id"] + "-01")
        self.assertEqual(rec["status"], "estimated")
        self.assertIsNone(rec["actual"])
        self.assertIsNone(rec["ai_assisted"])
        self.assertEqual(rec["pert"], 9.33)

    def test_same_second_reruns_get_distinct_run_ids(self):
        a = self.append()
        b = self.append()
        self.assertNotEqual(a["run_id"], b["run_id"])
        ids = [json.loads(l)["id"] for l in self.raw_lines()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rejects_unknown_category(self):
        with self.assertRaises(ec.CalcError):
            self.append(tasks=[{"task": "x", "category": "nope", "tags": [],
                                "o": 1, "m": 2, "p": 3}])

    def test_rejects_bad_three_point(self):
        with self.assertRaises(ec.CalcError):
            self.append(tasks=[{"task": "x", "category": "docs", "tags": [],
                                "o": 5, "m": 2, "p": 3}])

    def test_lock_contention_fails_fast(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        lock = self.path + ".lock"
        open(lock, "w").close()
        try:
            with self.assertRaises(ec.CalcError):
                ec.cmd_append_history({
                    "history_path": self.path, "slug": "x",
                    "tasks": [{"task": "x", "category": "docs", "tags": [],
                               "o": 1, "m": 2, "p": 3}],
                    "lock_timeout": 0.2,
                })
        finally:
            os.remove(lock)
        # ロック解放後は通常の追記が成功する。
        out = self.append()
        self.assertEqual(out["appended"], 1)


class TestReadHistory(HistoryBase):
    def test_missing_file_is_empty_not_error(self):
        records, warnings = ec.read_history(self.path)
        self.assertEqual(records, [])
        self.assertEqual(warnings, [])

    def test_distinguishes_parse_and_schema_warnings(self):
        self.append()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
            fh.write(json.dumps({"schema_version": 2, "id": "x"}) + "\n")
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 1)
        kinds = sorted(w["kind"] for w in warnings)
        self.assertEqual(kinds, ["parse_error", "schema_violation"])

    def test_v1_records_skipped_with_warning(self):
        # v1 の 'pert' は異なる式で計算されていたため、キャリブレーションへ混在させると
        # actual/pert 比率が壊れる。
        self.append()
        rec = json.loads(self.raw_lines()[0])
        rec["schema_version"] = 1
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 1)
        self.assertEqual(warnings[0]["kind"], "schema_violation")

    def test_future_schema_version_skipped_with_warning(self):
        self.append()
        rec = json.loads(self.raw_lines()[0])
        rec["schema_version"] = 999
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 1)
        self.assertEqual(warnings[0]["kind"], "schema_violation")

    def test_unknown_extra_fields_tolerated(self):
        self.append()
        rec = json.loads(self.raw_lines()[0])
        rec["id"] = rec["id"] + "-extra"
        rec["future_field"] = {"x": 1}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 2)
        self.assertEqual(warnings, [])



class TestUpdateActual(HistoryBase):
    def test_updates_matching_record(self):
        out = self.append()
        task_id = out["run_id"] + "-01"
        res = ec.cmd_update_actual(self.path, task_id, 6.5, True)
        self.assertEqual(res["updated"]["actual"], 6.5)
        self.assertIs(res["updated"]["ai_assisted"], True)
        self.assertEqual(res["updated"]["status"], "done")
        rec = json.loads(self.raw_lines()[0])
        self.assertEqual(rec["actual"], 6.5)

    def test_rejects_nonpositive_actual(self):
        out = self.append()
        task_id = out["run_id"] + "-01"
        for bad in (0, -3):
            with self.assertRaises(ec.CalcError):
                ec.cmd_update_actual(self.path, task_id, bad, False)

    def test_unknown_id_errors(self):
        self.append()
        with self.assertRaises(ec.CalcError):
            ec.cmd_update_actual(self.path, "nope-01", 5, False)

    def test_preserves_corrupt_lines_verbatim(self):
        out = self.append()
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("{corrupt line\n")
        ec.cmd_update_actual(self.path, out["run_id"] + "-01", 5, False)
        self.assertIn("{corrupt line", self.raw_lines())

    def test_lock_contention_fails_fast(self):
        out = self.append()
        lock = self.path + ".lock"
        open(lock, "w").close()
        try:
            with self.assertRaises(ec.CalcError):
                ec.cmd_update_actual(
                    self.path, out["run_id"] + "-01", 5, False, lock_timeout=0.2
                )
        finally:
            os.remove(lock)


def _done_record(i, category="backend-api", tags=(), pert=10.0, actual=10.0,
                 ai=False, date="2026-06-01"):
    return {
        "schema_version": 2, "run_id": f"r{i}", "id": f"r{i}-01", "date": date,
        "task": f"past task {i}", "category": category, "tags": list(tags),
        "o": pert * 0.5, "m": pert, "p": pert * 2, "pert": pert,
        "actual": actual, "ai_assisted": ai, "status": "done",
    }


class TestReferenceClass(HistoryBase):
    def write_done(self, records):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def test_insufficient_data_skips_correction_but_returns_anchors(self):
        self.write_done([_done_record(i, tags=["auth"]) for i in range(3)])
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": ["auth"]}],
        })
        entry = out["tasks"][0]
        self.assertEqual(entry["correction"], {"skipped": "insufficient_data", "count": 3})
        self.assertEqual(len(entry["anchors"]), 3)

    def test_correction_uses_ratio_percentiles(self):
        # actual/pert 比率: 1.0, 1.0, 1.0, 2.0, 2.0 → p50 = 1.0
        recs = [_done_record(i, actual=10.0) for i in range(3)]
        recs += [_done_record(i + 3, actual=20.0) for i in range(2)]
        self.write_done(recs)
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": [],
                       "m": 8, "p": 16}],
        })
        corr = out["tasks"][0]["correction"]
        self.assertEqual(corr["count"], 5)
        self.assertEqual(corr["ratio_p50"], 1.0)
        self.assertEqual(corr["corrected_m"], 8.0)
        self.assertEqual(corr["corrected_p"], round(16 * corr["ratio_p80"], 2))

    def test_anchors_ranked_by_tag_overlap(self):
        self.write_done([
            _done_record(1, tags=["auth", "rest"]),
            _done_record(2, tags=["ui"]),
            _done_record(3, tags=["auth"]),
        ])
        out = ec.cmd_reference_class({
            "history_path": self.path, "max_anchors": 2,
            "tasks": [{"name": "t", "category": "backend-api",
                       "tags": ["auth", "rest"]}],
        })
        anchors = out["tasks"][0]["anchors"]
        self.assertEqual(len(anchors), 2)
        self.assertEqual(anchors[0]["task"], "past task 1")

    def test_other_categories_excluded(self):
        self.write_done([_done_record(1, category="docs")])
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": []}],
        })
        self.assertEqual(out["tasks"][0]["anchors"], [])

    def test_corrected_o_gets_ratio_correction_and_stays_below_corrected_m(self):
        # 5レコードすべての actual/pert 比率が 0.4 → r50 = 0.4
        recs = [_done_record(i, pert=10.0, actual=4.0) for i in range(5)]
        self.write_done(recs)
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": [],
                       "o": 4, "m": 8, "p": 16}],
        })
        corr = out["tasks"][0]["correction"]
        self.assertEqual(corr["corrected_m"], 3.2)
        self.assertEqual(corr["corrected_o"], 1.6)  # 4 * 0.4
        self.assertLessEqual(corr["corrected_o"], corr["corrected_m"])

    def test_correction_prefers_tag_matched_pool(self):
        # タグ一致の5レコードは比率 2.0、タグなしの5レコードは比率 1.0。
        # 補正はアンカーが示すタグ一致の母集団から求めなければならない。
        recs = [_done_record(i, tags=["auth"], actual=20.0) for i in range(5)]
        recs += [_done_record(i + 5, actual=10.0) for i in range(5)]
        self.write_done(recs)
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": ["auth"],
                       "m": 8, "p": 16}],
        })
        corr = out["tasks"][0]["correction"]
        self.assertEqual(corr["basis"], "category_and_tags")
        self.assertEqual(corr["count"], 5)
        self.assertEqual(corr["ratio_p50"], 2.0)

    def test_correction_falls_back_to_category_when_tag_pool_small(self):
        recs = [_done_record(i, actual=10.0) for i in range(5)]
        recs.append(_done_record(9, tags=["auth"], actual=20.0))
        self.write_done(recs)
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": ["auth"],
                       "m": 8, "p": 16}],
        })
        corr = out["tasks"][0]["correction"]
        self.assertEqual(corr["basis"], "category")
        self.assertEqual(corr["count"], 6)

    def test_correction_flags_low_sample(self):
        small = [_done_record(i, actual=10.0) for i in range(5)]
        self.write_done(small)
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": [],
                       "m": 8, "p": 16}],
        })
        self.assertTrue(out["tasks"][0]["correction"]["low_sample"])

    def test_correction_omits_low_sample_when_enough_records(self):
        recs = [_done_record(i, actual=10.0) for i in range(10)]
        self.write_done(recs)
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": [],
                       "m": 8, "p": 16}],
        })
        self.assertNotIn("low_sample", out["tasks"][0]["correction"])

    def test_rejects_invalid_min_records_and_max_anchors(self):
        self.write_done([_done_record(1)])
        for override in (
            {"min_records": 0},
            {"min_records": "5"},
            {"min_records": True},
            {"max_anchors": -1},
            {"max_anchors": 2.5},
        ):
            payload = {
                "history_path": self.path,
                "tasks": [{"name": "t", "category": "backend-api", "tags": []}],
                **override,
            }
            with self.subTest(override=override), self.assertRaises(ec.CalcError):
                ec.cmd_reference_class(payload)

    def test_missing_ai_assisted_key_does_not_raise(self):
        rec = _done_record(1)
        del rec["ai_assisted"]
        self.write_done([rec])
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": []}],
        })
        self.assertIsNone(out["tasks"][0]["anchors"][0]["ai_assisted"])


class TestCalibration(TestReferenceClass):
    def test_no_completed_records(self):
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["skipped"], "no_completed_records")

    def test_bias_detection(self):
        self.write_done([_done_record(i, actual=15.0) for i in range(4)])  # ratio 1.5
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["count"], 4)
        self.assertEqual(out["ratio_p50"], 1.5)
        self.assertEqual(out["bias"], "underestimating")
        self.assertEqual(out["by_category"]["backend-api"]["count"], 4)

    def test_ai_factor_requires_three_of_each(self):
        recs = [_done_record(i, actual=5.0, ai=True) for i in range(3)]      # 0.5
        recs += [_done_record(i + 3, actual=10.0, ai=False) for i in range(3)]  # 1.0
        self.write_done(recs)
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(
            out["ai_assistance_factors"]["backend-api"]["factor"], 0.5
        )
        self.assertTrue(out["ai_assistance_factors"]["backend-api"]["low_sample"])

    def test_low_sample_flag_reflects_record_count(self):
        self.write_done([_done_record(i) for i in range(4)])
        self.assertTrue(ec.cmd_calibration({"history_path": self.path})["low_sample"])
        self.write_done([_done_record(i + 4) for i in range(6)])
        self.assertNotIn(
            "low_sample", ec.cmd_calibration({"history_path": self.path})
        )

    def test_ai_factor_absent_when_sparse(self):
        recs = [_done_record(1, ai=True), _done_record(2, ai=False)]
        self.write_done(recs)
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["ai_assistance_factors"], {})

    def test_missing_ai_assisted_key_does_not_raise(self):
        # AI 3件、人間 3件に加え、キー自体が存在しないレコードを1件追加する。
        # schema_error は .get のみを検査するため、このレコードもスキーマ上は有効である。
        recs = [_done_record(i, actual=5.0, ai=True) for i in range(3)]
        recs += [_done_record(i + 3, actual=10.0, ai=False) for i in range(3)]
        no_key = _done_record(99)
        del no_key["ai_assisted"]
        recs.append(no_key)
        self.write_done(recs)
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["count"], 7)
        # キーがないレコードは AI・人間のいずれのグループからも除外される。
        self.assertEqual(
            out["ai_assistance_factors"]["backend-api"]["ai_count"], 3
        )
        self.assertEqual(
            out["ai_assistance_factors"]["backend-api"]["human_count"], 3
        )


class TestPipeline(HistoryBase):
    VALID_CONTEXT = {
        "comparison_key": "A-AR-001",
        "qa_included": True,
        "ai_view": True,
        "analysis_mode": "quality",
        "hours_per_day": 8,
        "correlation": 0.3,
        "sources": ["spec.md"],
        "scope": "in scope",
        "exclusions": ["ops"],
        "dependencies": ["API"],
        "assumptions": ["pattern exists"],
    }
    def write_done(self, records):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def payload(self, **over):
        base = {
            "history_path": self.path,
            "slug": "feat",
            "analysis": {
                "mode": "quality",
                "agents": ["spec-analyzer", "code-analyzer"],
            },
            "tasks": [
                {"task": "Add endpoint", "category": "backend-api",
                 "tags": ["auth"], "o": 4, "m": 8, "p": 16,
                 "default_factor": 0.55},
                {"task": "Write guide", "category": "docs", "tags": [],
                 "o": 1, "m": 2, "p": 3, "default_factor": 0.50},
            ],
            "trials": 500,
            "seed": 42,
        }
        base.update(over)
        return base

    def test_pipeline_rejects_invalid_v3_run_context_before_history_write(self):
        with self.assertRaisesRegex(ec.CalcError, "run_context.*comparison_key"):
            ec.cmd_pipeline(self.payload(run_context={}))
        self.assertFalse(os.path.exists(self.path))

    def test_read_history_accepts_existing_v2_and_valid_v3_records(self):
        self.append()
        ec.cmd_pipeline(self.payload(run_context=self.VALID_CONTEXT))
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 3)
        self.assertEqual(warnings, [])
        self.assertEqual(records[-1]["schema_version"], 3)

    def test_v3_run_summary_preserves_reproduction_seeds(self):
        out = ec.cmd_pipeline(self.payload(run_context=self.VALID_CONTEXT))
        rec = json.loads(self.raw_lines()[0])
        self.assertEqual(rec["run_summary"]["simulation"]["traditional_seed"],
                         out["simulation"]["traditional_seed"])
        self.assertEqual(rec["run_summary"]["simulation"]["ai_assisted_seed"],
                         out["simulation"]["ai_assisted_seed"])

    def test_run_context_allows_zero_correlation(self):
        context = dict(self.VALID_CONTEXT, correlation=0)
        out = ec.cmd_pipeline(self.payload(run_context=context))
        self.assertEqual(out["run_context"]["correlation"], 0)

    def test_returns_analysis_and_simulation_without_summary(self):
        analysis = {"mode": "economy", "agents": ["spec-analyzer"]}
        out = ec.cmd_pipeline(self.payload(analysis=analysis))
        self.assertEqual(out["analysis"], analysis)
        self.assertEqual(out["simulation"]["distribution"], "triangular")
        self.assertNotIn("summary", out)

    def test_pipeline_writes_history_without_a_runs_directory(self):
        out = ec.cmd_pipeline(self.payload())
        self.assertEqual(len(self.raw_lines()), 2)
        self.assertFalse(os.path.exists(os.path.join(
            os.path.dirname(self.path), "runs", out["run_id"] + ".json"
        )))

    def test_pipeline_returns_granularity_warnings_without_blocking_history_write(self):
        tasks = [
            {"task": "Small", "category": "backend-api", "tags": [],
             "o": 1, "m": 3, "p": 5, "default_factor": 0.5},
            {"task": "Boundary low", "category": "backend-api", "tags": [],
             "o": 2, "m": 4, "p": 6, "default_factor": 0.5},
            {"task": "Boundary high", "category": "backend-api", "tags": [],
             "o": 12, "m": 24, "p": 30, "default_factor": 0.5},
            {"task": "Large", "category": "backend-api", "tags": [],
             "o": 20, "m": 25, "p": 40, "default_factor": 0.5},
        ]
        out = ec.cmd_pipeline(self.payload(tasks=tasks, run_context=self.VALID_CONTEXT))
        self.assertEqual(
            [w["kind"] for w in out["granularity_warnings"]],
            ["below_recommended", "above_recommended"],
        )
        self.assertEqual(
            out["granularity_warnings"][0],
            {"task": "Small", "field": "m", "value": 3,
             "kind": "below_recommended"},
        )
        self.assertEqual(len(self.raw_lines()), 4)

    def test_run_summary_is_not_a_payload_command(self):
        self.assertNotIn("run-summary", ec.PAYLOAD_COMMANDS)

    def test_rejects_analysis_before_history_write(self):
        for analysis in (
            {"mode": [], "agents": ["spec-analyzer"]},
            {"mode": {}, "agents": ["spec-analyzer"]},
            {"mode": "economy", "agents": []},
            {"mode": "economy", "agents": [1]},
            {"mode": "economy", "agents": [None]},
            {"mode": "economy", "agents": [["spec-analyzer"]]},
            {"mode": "economy", "agents": [{"name": "spec-analyzer"}]},
        ):
            with self.subTest(analysis=analysis), self.assertRaises(ec.CalcError):
                ec.cmd_pipeline(self.payload(analysis=analysis))
            self.assertFalse(os.path.exists(self.path))

    def test_returns_the_reproduction_parameters_to_its_caller(self):
        # レポートテンプレートは distribution/trials/seed を記載し、スキルはこの
        # 返却値を読む。そのため、正しくレポートを埋めるにはここで返す必要がある。
        out = ec.cmd_pipeline(self.payload())
        self.assertEqual(out["simulation"]["distribution"], "triangular")

    def test_history_schema_version_is_unaffected_by_the_run_bump(self):
        # 履歴スキーマは出力形式の変更から独立している。将来の履歴スキーマ更新を
        # 意図的なものにするため、リテラル値へ固定する。
        out = ec.cmd_pipeline(self.payload())
        recs = [json.loads(l) for l in self.raw_lines()]
        self.assertEqual({r["schema_version"] for r in recs}, {2})
        self.assertEqual(out["run_id"], recs[0]["run_id"])

    def test_unseeded_pipeline_run_stays_reproducible(self):
        payload = self.payload()
        del payload["seed"]
        out = ec.cmd_pipeline(payload)
        sim = out["simulation"]
        replay = ec.cmd_simulate({
            "tasks": [{"name": t["task"], "o": t["o"], "m": t["m"], "p": t["p"]}
                      for t in out["tasks"]],
            "trials": sim["trials"], "correlation": sim["correlation"],
            "hours_per_day": sim["hours_per_day"],
            "seed": sim["traditional_seed"],
        })
        self.assertEqual(replay["total"]["p50"], out["traditional"]["p50"])
        self.assertEqual(replay["total"]["p80"], out["traditional"]["p80"])

    def test_cold_start_runs_whole_flow(self):
        out = ec.cmd_pipeline(self.payload())
        self.assertEqual(out["tasks"][0]["id"], out["run_id"] + "-01")
        self.assertEqual(
            out["tasks"][0]["correction"],
            {"skipped": "insufficient_data", "count": 0},
        )
        self.assertEqual(out["tasks"][0]["o"], 4)  # uncorrected
        self.assertEqual(
            out["tasks"][0]["ai_factor"], {"factor": 0.55, "source": "default"}
        )
        self.assertLess(out["ai_assisted"]["p80"], out["traditional"]["p80"])
        # 履歴だけが永続化される出力である。
        recs = [json.loads(l) for l in self.raw_lines()]
        self.assertEqual([r["run_id"] for r in recs], [out["run_id"]] * 2)

    def test_applies_reference_class_correction(self):
        # actual/pert = 2.0 の完了済み backend-api レコードが5件。
        self.write_done([
            _done_record(i, tags=["auth"], actual=20.0) for i in range(5)
        ])
        out = ec.cmd_pipeline(self.payload(ai_view=False))
        t = out["tasks"][0]
        self.assertEqual(t["correction"]["ratio_p50"], 2.0)
        self.assertEqual(t["m"], 16.0)   # 8 * 2.0
        self.assertEqual(t["p"], 32.0)   # 16 * 2.0
        # 補正後の値が永続化される。
        rec = json.loads(self.raw_lines()[5])
        self.assertEqual(rec["m"], 16.0)

    def test_learned_factor_wins_over_default(self):
        recs = [_done_record(i, actual=5.0, ai=True) for i in range(3)]
        recs += [_done_record(i + 3, actual=10.0, ai=False) for i in range(3)]
        self.write_done(recs)
        out = ec.cmd_pipeline(self.payload())
        self.assertEqual(out["tasks"][0]["ai_factor"], {
            "factor": 0.5, "source": "learned", "low_sample": True,
        })
        self.assertEqual(
            out["tasks"][1]["ai_factor"], {"factor": 0.50, "source": "default"}
        )

    def test_missing_default_factor_fails_before_any_write(self):
        payload = self.payload()
        del payload["tasks"][1]["default_factor"]
        with self.assertRaisesRegex(ec.CalcError, "default_factor"):
            ec.cmd_pipeline(payload)
        self.assertFalse(os.path.exists(self.path))

    def test_simulation_params_pass_through(self):
        out = ec.cmd_pipeline(self.payload(correlation=0.7, hours_per_day=6))
        self.assertEqual(out["correlation"], 0.7)
        self.assertEqual(out["hours_per_day"], 6)
        self.assertAlmostEqual(
            out["traditional"]["p80_days"],
            out["traditional"]["p80"] / 6, delta=0.01,
        )

    def test_rejects_unknown_category(self):
        payload = self.payload()
        payload["tasks"][0]["category"] = "nope"
        with self.assertRaisesRegex(ec.CalcError, "pipeline.*category"):
            ec.cmd_pipeline(payload)
        self.assertFalse(os.path.exists(self.path))

    def test_rejects_empty_tasks(self):
        with self.assertRaisesRegex(ec.CalcError, "tasks"):
            ec.cmd_pipeline(self.payload(tasks=[]))
        self.assertFalse(os.path.exists(self.path))

    def test_rejects_non_bool_ai_view(self):
        with self.assertRaisesRegex(ec.CalcError, "ai_view"):
            ec.cmd_pipeline(self.payload(ai_view="true"))
        self.assertFalse(os.path.exists(self.path))

    def test_rejects_invalid_three_point_before_any_write(self):
        payload = self.payload()
        payload["tasks"][0]["o"] = 99  # o > m
        with self.assertRaises(ec.CalcError):
            ec.cmd_pipeline(payload)
        self.assertFalse(os.path.exists(self.path))

    def test_reference_class_default_max_anchors_is_three(self):
        # タグ一致の完了済みレコードが5件ある。reference-class はデフォルトで
        # アンカーを3件だけ返し、縮約された o/m/p フィールドは返さない。
        self.write_done([
            _done_record(i, tags=["auth"], date=f"2026-06-0{i + 1}")
            for i in range(5)
        ])
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": ["auth"]}],
        })
        anchors = out["tasks"][0]["anchors"]
        self.assertEqual(len(anchors), 3)
        for anchor in anchors:
            self.assertEqual(
                set(anchor.keys()),
                {"task", "pert", "actual", "ai_assisted", "tags"},
            )

    def test_is_registered_as_payload_command(self):
        self.assertIs(ec.PAYLOAD_COMMANDS["pipeline"], ec.cmd_pipeline)


class TestCompareRuns(HistoryBase):
    def _payload(self, slug):
        return {"history_path": self.path, "slug": slug,
                "analysis": {"mode": "quality", "agents": ["spec-analyzer", "code-analyzer"]},
                "tasks": [{"task": "Task", "category": "backend-api", "tags": [],
                            "o": 4, "m": 8, "p": 12, "default_factor": 0.5}],
                "run_context": TestPipeline.VALID_CONTEXT, "trials": 20, "seed": 1}
    def test_compare_runs_reports_context_and_totals(self):
        base = ec.cmd_pipeline(self._payload("base"))
        cand = ec.cmd_pipeline(self._payload("candidate"))
        out = ec.cmd_compare_runs({"history_path": self.path,
                                   "baseline_run_id": base["run_id"],
                                   "candidate_run_id": cand["run_id"]})
        self.assertTrue(out["comparable"])
        self.assertEqual(out["context_diff"], {})
        self.assertIn("p50", out["totals"]["baseline"])
        self.assertIn("task_sums", out["totals"]["baseline"])
        self.assertEqual(out["totals"]["baseline"]["task_sums"]["m"], 8)

    def test_compare_runs_marks_legacy_not_comparable(self):
        legacy = self.append()
        cand = ec.cmd_pipeline(self._payload("candidate"))
        out = ec.cmd_compare_runs({"history_path": self.path,
                                   "baseline_run_id": legacy["run_id"],
                                   "candidate_run_id": cand["run_id"]})
        self.assertFalse(out["comparable"])
        self.assertEqual(out["reason"], "missing_run_context")

    def test_compare_runs_reports_non_unique_context(self):
        base = ec.cmd_pipeline(self._payload("base"))
        lines = self.raw_lines()
        rec = json.loads(lines[0])
        rec["run_context"] = dict(rec["run_context"], scope="changed")
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
        out = ec.cmd_compare_runs({"history_path": self.path,
                                   "baseline_run_id": base["run_id"],
                                   "candidate_run_id": base["run_id"]})
        self.assertEqual(out["reason"], "non_unique_run_context")


class TestDistribute(unittest.TestCase):
    def test_proportional_split_sums_to_total(self):
        out = ec.cmd_distribute({
            "total": 10,
            "tasks": [{"id": "a", "pert": 2.0}, {"id": "b", "pert": 6.0},
                      {"id": "c", "pert": 2.0}],
        })
        shares = {s["id"]: s["actual"] for s in out["shares"]}
        self.assertEqual(shares, {"a": 2.0, "b": 6.0, "c": 2.0})
        self.assertAlmostEqual(sum(shares.values()), 10)

    def test_rounding_remainder_distributed(self):
        out = ec.cmd_distribute({
            "total": 10,
            "tasks": [{"id": "a", "pert": 1.0}, {"id": "b", "pert": 1.0},
                      {"id": "c", "pert": 1.0}],
        })
        self.assertAlmostEqual(sum(s["actual"] for s in out["shares"]), 10)

    def test_rejects_nonpositive_total_or_pert(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_distribute({"total": 0, "tasks": [{"id": "a", "pert": 1}]})
        with self.assertRaises(ec.CalcError):
            ec.cmd_distribute({"total": 5, "tasks": [{"id": "a", "pert": 0}]})

    def test_skewed_perts_never_produce_negative_share(self):
        tasks = [{"id": f"t{i}", "pert": 1.0} for i in range(19)]
        tasks.append({"id": "tiny", "pert": 0.001})
        out = ec.cmd_distribute({"total": 100, "tasks": tasks})
        self.assertTrue(all(s["actual"] >= 0 for s in out["shares"]))
        self.assertAlmostEqual(sum(s["actual"] for s in out["shares"]), 100)


class TestMainErrorContract(unittest.TestCase):
    def test_unexpected_exception_emits_error_json(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = ec.main(["simulate", "--input", "/nonexistent/file.json"])
        self.assertEqual(rc, 1)
        self.assertIn("error", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
