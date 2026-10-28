import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / ".codex" / "agents"
GENERATE = ROOT / "scripts" / "generate-codex-agents.py"
INSTALL = ROOT / "scripts" / "install-codex-agents.sh"
REQUIRED = ("estimate-spec-analyzer", "estimate-code-analyzer")


class TestCodexAgents(unittest.TestCase):
    def test_generated_toml_matches_agents_md(self):
        result = subprocess.run(
            ["python3", str(GENERATE), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_required_keys_and_names(self):
        for name in REQUIRED:
            path = SRC / ("%s.toml" % name)
            text = path.read_text(encoding="utf-8")
            self.assertIn('name = "%s"' % name, text)
            self.assertIn("description = ", text)
            self.assertIn("developer_instructions = ", text)
            for line in text.splitlines():
                self.assertFalse(
                    line.startswith("model ")
                    or line.startswith("tools ")
                    or line.startswith("sandbox_mode "),
                    msg=path,
                )

    def test_install_check_detects_stale_and_missing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            install = subprocess.run(
                ["bash", str(INSTALL), "--dest", str(dest)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            check = subprocess.run(
                ["bash", str(INSTALL), "--check", "--dest", str(dest)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

            target = dest / "estimate-spec-analyzer.toml"
            with target.open("a", encoding="utf-8") as fh:
                fh.write("stale\n")
            stale = subprocess.run(
                ["bash", str(INSTALL), "--check", "--dest", str(dest)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("stale", stale.stdout)

            os.remove(dest / "estimate-code-analyzer.toml")
            missing = subprocess.run(
                ["bash", str(INSTALL), "--check", "--dest", str(dest)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("not installed", missing.stdout)

    def test_project_flag_writes_cwd_codex_agents(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            result = subprocess.run(
                ["bash", str(INSTALL), "--project"],
                cwd=project,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            copied = project / ".codex" / "agents" / "estimate-spec-analyzer.toml"
            self.assertTrue(copied.is_file())
            self.assertEqual(
                copied.read_text(encoding="utf-8"),
                (SRC / "estimate-spec-analyzer.toml").read_text(encoding="utf-8"),
            )
