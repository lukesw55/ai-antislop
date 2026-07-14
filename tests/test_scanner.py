"""Tests for scripts/scan_repo_slop.py — run via: python3 -m unittest discover tests"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCANNER = Path(__file__).resolve().parent.parent / "anti-slop" / "scripts" / "scan_repo_slop.py"


def run_scanner(*args):
    command = [sys.executable, str(SCANNER), *args]
    if "--json" not in args and "--json-v2" not in args:
        command.append("--json")
    return subprocess.run(
        command,
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

    def test_json_v2_reports_multiple_findings_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "README.md").write_text(
                "A production-ready, robust, revolutionary tool using a generated image.\n",
                encoding="utf-8",
            )
            proc = run_scanner(tmp, "--json-v2", "--max-findings", "2")
            again = run_scanner(tmp, "--json-v2", "--max-findings", "2")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(len(payload["findings"]), 2)
        self.assertGreaterEqual(payload["summary"]["total_findings"], 4)
        self.assertTrue(payload["truncated"])
        self.assertEqual(
            payload["omitted_findings"],
            payload["summary"]["total_findings"] - len(payload["findings"]),
        )
        self.assertIn("output truncated", proc.stderr)
        self.assertIn("rule_id", payload["findings"][0])
        self.assertIn("impact", payload["findings"][0])
        self.assertEqual(proc.stdout, again.stdout)

    def test_fail_on_thresholds_include_stricter_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = {
                "block.md": ("production-ready\n", {"block": 2, "trim": 2, "flag": 2}),
                "trim.md": ("A robust tool.\n", {"block": 0, "trim": 2, "flag": 2}),
                "flag.md": ("A generated image.\n", {"block": 0, "trim": 0, "flag": 2}),
            }
            for filename, (text, expected) in cases.items():
                path = root / filename
                path.write_text(text, encoding="utf-8")
                for threshold, returncode in expected.items():
                    with self.subTest(filename=filename, threshold=threshold):
                        proc = run_scanner(str(path), "--fail-on", threshold)
                        self.assertEqual(proc.returncode, returncode, proc.stderr)

    def test_max_file_bytes_skips_content_and_reports_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "large.md")
            path.write_text("production-ready " + ("x" * 128), encoding="utf-8")
            proc = run_scanner(
                str(path),
                "--json-v2",
                "--max-file-bytes",
                "16",
                "--fail-on-block",
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["summary"]["files_skipped_too_large"], 1)
        self.assertIn("content skipped", proc.stderr)

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

    def test_default_excludes_hybrid_runtime_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            directories = {".agents", ".claude", ".codex", ".cursor"}
            for directory in directories:
                vendored = Path(tmp, directory)
                vendored.mkdir()
                (vendored / "doc.md").write_text(
                    "Fully automated, production-ready.\n", encoding="utf-8"
                )
            proc = run_scanner(tmp)
            self.assertEqual(findings_of(proc), [])
            proc = run_scanner(tmp, "--no-default-excludes")
            paths = {finding["path"].split("/", 1)[0] for finding in findings_of(proc)}
            self.assertEqual(paths, directories)

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

    def test_gitignored_paths_skipped_in_git_repo(self):
        if not shutil.which("git"):
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "-C", tmp, "init", "-q"], check=True, timeout=30)
            (root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
            (root / "README.md").write_text("# clean\n\nJust the facts.\n", encoding="utf-8")
            scratch = root / "scratch"
            scratch.mkdir()
            (scratch / "fixture.md").write_text("Enterprise-grade, battle-tested.\n", encoding="utf-8")
            proc = run_scanner(tmp, "--fail-on-block")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(findings_of(proc), [])

    def test_git_worktree_file_respects_ignored_paths(self):
        if not shutil.which("git"):
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = root / "repository"
            worktree = root / "linked-worktree"
            repository.mkdir()
            subprocess.run(
                ["git", "-C", str(repository), "init", "-q"],
                check=True,
                capture_output=True,
                timeout=30,
            )
            (repository / ".gitignore").write_text("scratch/\n", encoding="utf-8")
            (repository / "README.md").write_text("# Facts\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repository), "add", "."],
                check=True,
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                [
                    "git", "-C", str(repository),
                    "-c", "user.name=Anti Slop Tests",
                    "-c", "user.email=tests@example.invalid",
                    "commit", "-qm", "fixture",
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            subprocess.run(
                [
                    "git", "-C", str(repository), "worktree", "add", "-q",
                    "-b", "scanner-linked-test", str(worktree),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            self.assertTrue((worktree / ".git").is_file())
            scratch = worktree / "scratch"
            scratch.mkdir()
            (scratch / "ignored.md").write_text(
                "Enterprise-grade and production-ready.\n", encoding="utf-8"
            )
            proc = run_scanner(str(worktree), "--fail-on-block")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(findings_of(proc), [])

    def test_own_repo_scan_is_block_clean(self):
        repo = str(SCANNER.parent.parent.parent)
        proc = subprocess.run(
            [sys.executable, str(SCANNER), repo, "--fail-on-block"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)


if __name__ == "__main__":
    unittest.main()
