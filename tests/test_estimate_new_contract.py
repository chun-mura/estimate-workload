import pathlib
import re
import unittest


SKILL = pathlib.Path(__file__).resolve().parent.parent / "skills" / "new" / "SKILL.md"


class TestEstimateNewQaContract(unittest.TestCase):
    def test_qa_is_default_and_can_only_be_explicitly_excluded(self):
        text = SKILL.read_text(encoding="utf-8")
        options = set(
            re.findall(
                r"(?<![\w-])--[a-z0-9]+(?:-[a-z0-9]+)*(?![\w-])",
                text,
                re.IGNORECASE,
            )
        )
        qa_options = {
            option
            for option in options
            if "qa" in option.removeprefix("--").lower().split("-")
        }
        self.assertSetEqual(
            qa_options,
            {"--no-qa"},
            "--no-qa must be the only QA-related option; do not add --qa or aliases",
        )
        self.assertIn("QA is included by default", text)
        self.assertIn("Test planning and test-case preparation", text)
        self.assertIn("Functional verification in an integrated environment", text)
        self.assertIn("Integration, E2E, and regression testing", text)
        self.assertIn("Defect verification and retesting", text)
        self.assertIn(
            "Unit tests and in-development checks remain part of implementation tasks",
            text,
        )
