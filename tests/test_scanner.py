"""Tests for scripts/scan_repo_slop.py — run via: python3 -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCANNER = Path(__file__).resolve().parent.parent / "anti-slop" / "scripts" / "scan_repo_slop.py"


def run_scanner(*args):
    return subprocess.run(
        [sys.executable, str(SCANNER), *args, "--json"],
        capture_output=True, text=True, timeout=60,
    )


def findings_of(proc):
    return json.loads(proc.stdout)


class ScannerTests(unittest.TestCase):
    def test_unquoted_claim_found_and_fails_on_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "README.md").write_text(
                "# tool\n\nThis tool is production-ready and battle-tested.\n",
                encoding="utf-8",
            )
            proc = run_scanner(tmp, "--fail-on-block")
        self.assertEqual(proc.returncode, 2)
        codes = {f["code"] for f in findings_of(proc)}
        self.assertIn("D2", codes)

    def test_quoted_mention_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "docs.md").write_text(
                '# banned words\n\n- "production-ready"\n- `battle-tested`\n'
                "- flag phrases like 'tests pass' in reviews\n",
                encoding="utf-8",
            )
            proc = run_scanner(tmp, "--fail-on-block")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(findings_of(proc), [])

    def test_match_inside_string_literal_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "rules.py").write_text(
                'PATTERN = re.compile(r"\\b(production[- ]ready|battle[- ]tested)\\b")\n',
                encoding="utf-8",
            )
            proc = run_scanner(tmp)
        self.assertEqual(findings_of(proc), [])

    def test_markdown_fence_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "example.md").write_text(
                "# doc\n\n```text\nAll tests passed. Enterprise-grade quality.\n```\n",
                encoding="utf-8",
            )
            proc = run_scanner(tmp)
        self.assertEqual(findings_of(proc), [])

    def test_default_exclude_claude_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            vendored = Path(tmp, ".claude", "skills", "anti-slop")
            vendored.mkdir(parents=True)
            (vendored / "doc.md").write_text("Fully automated, production-ready.\n", encoding="utf-8")
            proc = run_scanner(tmp)
            self.assertEqual(findings_of(proc), [])
            proc = run_scanner(tmp, "--no-default-excludes")
            self.assertNotEqual(findings_of(proc), [])

    def test_exclude_glob_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "vendor").mkdir()
            Path(tmp, "vendor", "x.md").write_text("Battle-tested framework.\n", encoding="utf-8")
            proc = run_scanner(tmp, "--exclude", "vendor/*")
            self.assertEqual(findings_of(proc), [])

    def test_disposable_filename_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "IMPLEMENTATION.md").write_text("I changed things.\n", encoding="utf-8")
            proc = run_scanner(tmp, "--fail-on-block")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("D1", {f["code"] for f in findings_of(proc)})

    def test_own_repo_scan_is_block_clean(self):
        repo = str(SCANNER.parent.parent.parent)
        proc = subprocess.run(
            [sys.executable, str(SCANNER), repo, "--fail-on-block"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()
