import pathlib
import unittest


SKILL = pathlib.Path(__file__).resolve().parent.parent / "skills" / "new" / "SKILL.md"


class TestEstimateNewQaContract(unittest.TestCase):
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
