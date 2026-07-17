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

    def test_pert_means(self):
        out = ec.cmd_simulate(self.payload())
        self.assertEqual(out["tasks"][0]["pert"], 8.67)
        self.assertEqual(out["tasks"][1]["pert"], 4.0)

    def test_seed_deterministic(self):
        a = ec.cmd_simulate(self.payload())
        b = ec.cmd_simulate(self.payload())
        self.assertEqual(a["total"], b["total"])

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
        self.assertEqual(out["tasks"][0]["pert"], 4.33)
        self.assertLessEqual(out["total"]["max"], 8)

    def test_rejects_bad_factor(self):
        with self.assertRaises(ec.CalcError):
            ec.cmd_simulate(
                {"tasks": [{"name": "x", "o": 4, "m": 8, "p": 16, "factor": 0}]}
            )

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
        self.assertEqual(rec["schema_version"], 1)
        self.assertEqual(rec["run_id"], out["run_id"])
        self.assertEqual(rec["id"], out["run_id"] + "-01")
        self.assertEqual(rec["status"], "estimated")
        self.assertIsNone(rec["actual"])
        self.assertIsNone(rec["ai_assisted"])
        self.assertEqual(rec["pert"], 8.67)

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
        # lock released -> a normal append now succeeds
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
            fh.write(json.dumps({"schema_version": 1, "id": "x"}) + "\n")
        records, warnings = ec.read_history(self.path)
        self.assertEqual(len(records), 1)
        kinds = sorted(w["kind"] for w in warnings)
        self.assertEqual(kinds, ["parse_error", "schema_violation"])

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


class TestRunSummary(HistoryBase):
    def setUp(self):
        super().setUp()
        self.output_dir = os.path.join(self.dir.name, ".estimate", "runs")
        self.appended = self.append(tasks=[
            {"task": "Add endpoint", "category": "backend-api", "tags": ["auth"],
             "o": 4, "m": 8, "p": 16},
            {"task": "Write guide", "category": "docs", "tags": ["readme"],
             "o": 1, "m": 2, "p": 3},
        ])

    def payload(self, **over):
        base = {
            "run_id": self.appended["run_id"],
            "history_path": self.path,
            "output_dir": self.output_dir,
            "traditional": {"mean": 20.5, "p50": 20.1, "p80": 24.3},
            "ai_assisted": {"mean": 10.0, "p50": 9.8, "p80": 12.0},
        }
        base.update(over)
        return base

    def test_writes_default_document_and_reads_tasks_from_history(self):
        out = ec.cmd_run_summary(self.payload())
        path = os.path.join(self.output_dir, self.appended["run_id"] + ".json")
        with open(path, encoding="utf-8") as fh:
            persisted = json.load(fh)
        self.assertEqual(persisted, out)
        self.assertEqual(out["schema_version"], 1)
        self.assertEqual(out["run_id"], self.appended["run_id"])
        datetime.fromisoformat(out["generated_at"])
        self.assertEqual(out["size"], {
            "label": "M",
            "basis": "ai_assisted_p80",
            "boundaries": {"s_max_hours": 4, "m_max_hours": 16},
        })
        self.assertEqual(out["traditional"], self.payload()["traditional"])
        self.assertEqual(out["ai_assisted"], self.payload()["ai_assisted"])
        self.assertEqual(out["tasks"], [
            {"id": self.appended["run_id"] + "-01", "task": "Add endpoint",
             "category": "backend-api", "pert": 8.67},
            {"id": self.appended["run_id"] + "-02", "task": "Write guide",
             "category": "docs", "pert": 2.0},
        ])

    def test_default_label_boundaries_are_inclusive(self):
        for p80, expected in ((4.0, "S"), (4.1, "M"), (16.0, "M"), (16.1, "L")):
            with self.subTest(p80=p80):
                ai = {"mean": p80, "p50": p80, "p80": p80}
                out = ec.cmd_run_summary(self.payload(ai_assisted=ai))
                self.assertEqual(out["size"]["label"], expected)

    def test_custom_and_partial_boundaries(self):
        ai = {"mean": 5, "p50": 5, "p80": 5}
        custom = ec.cmd_run_summary(self.payload(
            ai_assisted=ai,
            boundaries={"s_max_hours": 6, "m_max_hours": 20},
        ))
        self.assertEqual(custom["size"]["label"], "S")
        self.assertEqual(custom["size"]["boundaries"], {
            "s_max_hours": 6, "m_max_hours": 20,
        })
        partial = ec.cmd_run_summary(self.payload(
            ai_assisted=ai,
            boundaries={"s_max_hours": 3},
        ))
        self.assertEqual(partial["size"]["label"], "M")
        self.assertEqual(partial["size"]["boundaries"], {
            "s_max_hours": 3, "m_max_hours": 16,
        })

    def test_creates_missing_output_directory(self):
        nested = os.path.join(self.dir.name, "missing", "runs")
        ec.cmd_run_summary(self.payload(output_dir=nested))
        self.assertTrue(os.path.isfile(
            os.path.join(nested, self.appended["run_id"] + ".json")
        ))

    def test_uses_default_output_directory_when_omitted(self):
        payload = self.payload()
        del payload["output_dir"]
        with contextlib.chdir(self.dir.name):
            ec.cmd_run_summary(payload)
        self.assertTrue(os.path.isfile(os.path.join(
            self.dir.name, ".estimate", "runs", self.appended["run_id"] + ".json"
        )))

    def test_rejects_missing_or_invalid_totals(self):
        bad_payloads = [
            self.payload(traditional={"mean": 1, "p50": 1}),
            self.payload(ai_assisted={"mean": 1, "p50": 1, "p80": -1}),
            self.payload(ai_assisted={"mean": 1, "p50": 1, "p80": True}),
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload), self.assertRaises(ec.CalcError):
                ec.cmd_run_summary(payload)

    def test_rejects_invalid_boundaries(self):
        for boundaries in (
            {"s_max_hours": 16, "m_max_hours": 16},
            {"s_max_hours": 0},
            {"m_max_hours": float("inf")},
        ):
            with self.subTest(boundaries=boundaries), self.assertRaises(ec.CalcError):
                ec.cmd_run_summary(self.payload(boundaries=boundaries))

    def test_rejects_unknown_run_id(self):
        with self.assertRaisesRegex(ec.CalcError, "no history records"):
            ec.cmd_run_summary(self.payload(run_id="unknown-run"))

    def test_rejects_invalid_required_strings(self):
        for override in (
            {"run_id": ""},
            {"history_path": None},
            {"output_dir": ""},
        ):
            with self.subTest(override=override), self.assertRaises(ec.CalcError):
                ec.cmd_run_summary(self.payload(**override))

    def test_rejects_run_id_that_would_escape_output_directory(self):
        record = json.loads(self.raw_lines()[0])
        record["run_id"] = "../escape"
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        with self.assertRaisesRegex(ec.CalcError, "run_id.*path"):
            ec.cmd_run_summary(self.payload(run_id="../escape"))
        self.assertFalse(os.path.exists(
            os.path.join(self.dir.name, ".estimate", "escape.json")
        ))

    def test_cli_echoes_the_persisted_document(self):
        payload_path = os.path.join(self.dir.name, "payload.json")
        with open(payload_path, "w", encoding="utf-8") as fh:
            json.dump(self.payload(), fh)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = ec.main(["run-summary", "--input", payload_path])
        self.assertEqual(rc, 0)
        echoed = json.loads(stdout.getvalue())
        with open(os.path.join(
            self.output_dir, self.appended["run_id"] + ".json"
        ), encoding="utf-8") as fh:
            persisted = json.load(fh)
        self.assertEqual(echoed, persisted)

    def test_is_registered_as_payload_command(self):
        self.assertIs(ec.PAYLOAD_COMMANDS["run-summary"], ec.cmd_run_summary)


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
        "schema_version": 1, "run_id": f"r{i}", "id": f"r{i}-01", "date": date,
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
        # actual/pert ratios: 1.0, 1.0, 1.0, 2.0, 2.0 -> p50 = 1.0
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

    def test_corrected_o_kept_below_corrected_m(self):
        # actual/pert ratio 0.4 for all 5 records -> r50 = 0.4
        recs = [_done_record(i, pert=10.0, actual=4.0) for i in range(5)]
        self.write_done(recs)
        out = ec.cmd_reference_class({
            "history_path": self.path,
            "tasks": [{"name": "t", "category": "backend-api", "tags": [],
                       "o": 4, "m": 8, "p": 16}],
        })
        corr = out["tasks"][0]["correction"]
        self.assertEqual(corr["corrected_m"], 3.2)
        self.assertEqual(corr["corrected_o"], 3.2)
        self.assertLessEqual(corr["corrected_o"], corr["corrected_m"])

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

    def test_ai_factor_absent_when_sparse(self):
        recs = [_done_record(1, ai=True), _done_record(2, ai=False)]
        self.write_done(recs)
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["ai_assistance_factors"], {})

    def test_missing_ai_assisted_key_does_not_raise(self):
        # 3 AI + 3 human records plus one record with the key entirely
        # absent (schema-valid per schema_error, which only checks .get).
        recs = [_done_record(i, actual=5.0, ai=True) for i in range(3)]
        recs += [_done_record(i + 3, actual=10.0, ai=False) for i in range(3)]
        no_key = _done_record(99)
        del no_key["ai_assisted"]
        recs.append(no_key)
        self.write_done(recs)
        out = ec.cmd_calibration({"history_path": self.path})
        self.assertEqual(out["count"], 7)
        # the keyless record is excluded from both ai and human groups
        self.assertEqual(
            out["ai_assistance_factors"]["backend-api"]["ai_count"], 3
        )
        self.assertEqual(
            out["ai_assistance_factors"]["backend-api"]["human_count"], 3
        )


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
