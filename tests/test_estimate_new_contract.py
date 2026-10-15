import json
import pathlib
import re
import sys
import unittest


SKILL = pathlib.Path(__file__).resolve().parent.parent / "skills" / "new" / "SKILL.md"
ROOT = SKILL.parent.parent.parent
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
CHANGELOG = ROOT / "CHANGELOG.md"


class TestEstimateNewQaContract(unittest.TestCase):
    def test_release_metadata_contract(self):
        plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], "0.12.0")
        changelog = CHANGELOG.read_text(encoding="utf-8")
        for required in ("0.10.0", "0.11.0", "粒度", "比較", "v3", "run_context"):
            self.assertIn(required, changelog)
        unreleased = changelog.split("## [Unreleased]", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(unreleased.strip(), "")
        release = changelog.split("## [0.11.0]", 1)[1].split("\n## ", 1)[0]
        for required in ("粒度", "比較", "run_context", "30%", "manual-verification"):
            self.assertIn(required, release)
        latest = changelog.split("## [0.12.0]", 1)[1].split("\n## ", 1)[0]
        for required in ("ai_sensitivity", "docs", "0.60"):
            self.assertIn(required, latest)

    def test_skill_requires_hour_units_context_and_reconciliation_gate(self):
        text = SKILL.read_text(encoding="utf-8")
        for required in ("--compare-to", "comparison_key", "granularity_warnings",
                         "O/M/P の単位は時間", "30%", "楽観・標準・悲観"):
            self.assertIn(required, text)

    def test_compare_to_has_strict_option_validation_and_risk_rule(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("--compare-to` value must be non-empty", text)
        self.assertIn("duplicate", text)
        self.assertIn("unknown leading", text)
        self.assertIn("## リスク", text)
        self.assertIn("リスク表に1行", text)

    def test_qa_is_default_and_can_only_be_explicitly_excluded(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("--no-qa", text)
        self.assertIn("No other option excludes QA.", text)
        self.assertIn("QA is included by default", text)
        self.assertIn("Test planning and test-case preparation", text)
        self.assertIn("Functional verification in an integrated environment", text)
        self.assertIn("Integration, E2E, and regression testing", text)
        self.assertIn("Defect verification and retesting", text)
        self.assertIn(
            "Unit tests and in-development checks remain part of implementation tasks",
            text,
        )


sys.path.insert(0, str(ROOT / "scripts"))
import estimate_calc as ec  # noqa: E402

REFS = SKILL.parent / "references"


SENSITIVITY_HEADING = "\n## Sensitivity range"


def _table_rows(path):
    rows = {}
    text = path.read_text(encoding="utf-8").split(SENSITIVITY_HEADING)[0]
    for line in text.splitlines():
        m = re.match(r"\| `([a-z-]+)` \| ([^|]+) \|", line)
        if m:
            rows[m.group(1)] = m.group(2).strip()
    return rows


def _sensitivity_rows(path):
    text = path.read_text(encoding="utf-8").split(SENSITIVITY_HEADING)[1]
    rows = {}
    for line in text.splitlines():
        m = re.match(r"\| `([a-z-]+)` \|(.+)\|$", line)
        if m:
            rows[m.group(1)] = [float(c) for c in m.group(2).split("|")]
    return rows


class TestAiFactorContract(unittest.TestCase):
    def test_every_category_has_a_default_factor_and_taxonomy_row(self):
        factors = _table_rows(REFS / "ai-assistance-factors.md")
        taxonomy = _table_rows(REFS / "category-taxonomy.md")
        self.assertEqual(set(factors), ec.CATEGORIES)
        self.assertEqual(set(taxonomy), ec.CATEGORIES)

    def test_default_factors_follow_field_evidence(self):
        factors = {k: float(v) for k, v in
                   _table_rows(REFS / "ai-assistance-factors.md").items()}
        self.assertEqual(factors, {
            "docs": 0.60, "test-only": 0.70, "backend-api": 0.80,
            "frontend-ui": 0.80, "db-migration": 0.85, "infra": 0.90,
            "manual-verification": 1.00,
        })

    def test_sensitivity_table_matches_calc_and_brackets_defaults(self):
        path = REFS / "ai-assistance-factors.md"
        defaults = {k: float(v) for k, v in _table_rows(path).items()}
        rows = _sensitivity_rows(path)
        self.assertEqual(set(rows), ec.CATEGORIES)
        for cat, (optimistic, central, conservative) in rows.items():
            self.assertEqual(optimistic, ec.AI_SENSITIVITY_FACTORS["optimistic"][cat])
            self.assertEqual(central, defaults[cat])
            self.assertEqual(conservative,
                             ec.AI_SENSITIVITY_FACTORS["conservative"][cat])
            self.assertLessEqual(optimistic, central, cat)
            self.assertLessEqual(central, conservative, cat)

    def test_factor_reference_cites_field_studies(self):
        text = (REFS / "ai-assistance-factors.md").read_text(encoding="utf-8")
        for required in ("Paradis", "Cui", "METR 2026", "Peng", "Noy & Zhang"):
            self.assertIn(required, text)

    def test_qa_execution_is_manual_verification(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("Test planning and test-case preparation as `docs`", text)
        self.assertIn(
            "Functional verification in an integrated environment; Integration, E2E, "
            "and regression testing; and Defect verification and retesting as "
            "`manual-verification`",
            text,
        )
        self.assertIn(
            "(writing new automated E2E test code is a separate `test-only` task)", text
        )
