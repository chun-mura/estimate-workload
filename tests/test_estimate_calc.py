import json
import os
import pathlib
import sys
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
