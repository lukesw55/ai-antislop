"""Tests for scripts/scan_repo_slop.py — run via: python3 -m unittest discover tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCANNER = Path(__file__).resolve().parent.parent / "anti-slop" / "scripts" / "scan_repo_slop.py"

ZEBRA_RULE = {
    "id": "T1-zebra",
    "code": "T1",
    "impact": "major",
    "decision": "TRIM",
    "scopes": ["repository"],
    "kind": "regex",
    "pattern": "\\bzebra\\b",
    "message": "zebra spotted",
    "fix": "remove the zebra",
}


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


def write(directory, name, text):
    path = Path(directory, name)
    path.write_text(text, encoding="utf-8")
    return path


def require_symlinks(test, directory):
    """Skip the caller when the platform or account cannot create symlinks."""
    target = Path(directory, "probe-target.txt")
    target.write_text("probe", encoding="utf-8")
    link = Path(directory, "probe-link.txt")
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        test.skipTest("symlinks are not supported in this environment")
    link.unlink()
    target.unlink()


def git_repo(directory):
    subprocess.run(["git", "-C", directory, "init", "-q"], check=True, timeout=30)


def git_add_all(directory):
    subprocess.run(
        ["git", "-C", directory, "add", "-A"], check=True, capture_output=True, timeout=30
    )


class SymlinkSafetyTests(unittest.TestCase):
    """The scanner must never read through a link, whatever it points at."""

    TRIGGER = "This library is production-ready and battle-tested.\n"

    def build(self, root, outside):
        require_symlinks(self, root)
        write(outside, "secret.md", self.TRIGGER)
        Path(root, "link.md").symlink_to(Path(outside, "secret.md"))
        write(root, "README.md", "# tool\n\nInstall with pip.\n")

    def assert_external_content_absent(self, proc, payload):
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["summary"]["files_skipped_symlink"], 1)
        self.assertFalse(payload["summary"]["scan_complete"])
        self.assertNotIn("production-ready", proc.stdout)
        self.assertNotIn("battle-tested", proc.stdout)

    def test_tracked_symlink_to_external_file_is_not_read(self):
        if not shutil.which("git"):
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            self.build(tmp, outside)
            git_repo(tmp)
            git_add_all(tmp)
            proc = run_scanner(tmp, "--json-v2")
            gated = run_scanner(tmp, "--json-v2", "--fail-on-incomplete")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assert_external_content_absent(proc, payload)
        self.assertEqual(gated.returncode, 3, gated.stderr)

    def test_untracked_symlink_is_not_read_by_the_walk_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            self.build(tmp, outside)
            proc = run_scanner(tmp, "--json-v2")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assert_external_content_absent(proc, payload)
        self.assertIn("symlink", proc.stderr)

    def test_symlink_to_a_file_inside_the_root_is_still_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            require_symlinks(self, tmp)
            real = write(tmp, "real.md", self.TRIGGER)
            Path(tmp, "alias.md").symlink_to(real)
            proc = run_scanner(tmp, "--json-v2")
        payload = json.loads(proc.stdout)
        self.assertEqual(
            [(f["path"], f["rule_id"]) for f in payload["findings"]],
            [("real.md", "D2-maturity-claim")],
        )
        self.assertEqual(payload["summary"]["files_skipped_symlink"], 1)

    def test_broken_symlink_is_counted_not_crashed_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            require_symlinks(self, tmp)
            Path(tmp, "dangling.md").symlink_to(Path(tmp, "gone.md"))
            proc = run_scanner(tmp, "--json-v2")
            gated = run_scanner(tmp, "--json-v2", "--fail-on-incomplete")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["summary"]["files_skipped_symlink"], 1)
        self.assertEqual(payload["summary"]["files_unreadable"], 0)
        self.assertEqual(gated.returncode, 3)

    def test_tracked_broken_symlink_is_counted(self):
        if not shutil.which("git"):
            self.skipTest("git not available")
        with tempfile.TemporaryDirectory() as tmp:
            require_symlinks(self, tmp)
            Path(tmp, "dangling.md").symlink_to(Path(tmp, "gone.md"))
            git_repo(tmp)
            git_add_all(tmp)
            proc = run_scanner(tmp, "--json-v2")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["summary"]["files_skipped_symlink"], 1)

    def test_symlinked_file_passed_directly_to_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            require_symlinks(self, tmp)
            write(outside, "secret.md", self.TRIGGER)
            link = Path(tmp, "link.md")
            link.symlink_to(Path(outside, "secret.md"))
            proc = run_scanner(str(link), "--json-v2")
            gated = run_scanner(str(link), "--json-v2", "--fail-on-incomplete")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["summary"]["files_skipped_symlink"], 1)
        self.assertNotIn("production-ready", proc.stdout)
        self.assertEqual(gated.returncode, 3)

    def test_symlinked_directory_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            require_symlinks(self, tmp)
            write(outside, "secret.md", self.TRIGGER)
            link = Path(tmp, "aliasdir")
            link.symlink_to(Path(outside), target_is_directory=True)
            proc = run_scanner(str(link), "--json-v2")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Symlinked directory targets are not supported", proc.stderr)
        self.assertNotIn("production-ready", proc.stdout)

    def test_filename_rule_applies_to_a_symlink_without_reading_it(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            require_symlinks(self, tmp)
            write(outside, "target.md", self.TRIGGER)
            Path(tmp, "SUMMARY.md").symlink_to(Path(outside, "target.md"))
            proc = run_scanner(tmp, "--json-v2", "--fail-on-block")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(
            [(f["path"], f["rule_id"], f["line"]) for f in payload["findings"]],
            [("SUMMARY.md", "D7-summary-file", 1)],
        )
        self.assertNotIn("production-ready", proc.stdout)
        self.assertEqual(payload["summary"]["files_skipped_symlink"], 1)

    def test_path_resolving_outside_the_root_is_refused(self):
        sys.path.insert(0, str(SCANNER.parent.parent))
        sys.path.insert(0, str(SCANNER.parent))
        import scan_repo_slop as scanner
        from lib.anti_slop_engine import load_rules

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            inside = Path(tmp)
            stray = write(outside, "stray.md", self.TRIGGER)
            result = scanner.scan_file(
                stray, Path(outside), load_rules(), 4 * 1024 * 1024, inside.resolve()
            )
        self.assertEqual(result.state, "outside_root")
        self.assertEqual(result.findings, [])


class IncompleteScanTests(unittest.TestCase):
    def test_complete_scan_passes_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "README.md", "# tool\n\nInstall with pip.\n")
            proc = run_scanner(tmp, "--json-v2", "--fail-on-incomplete")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(payload["summary"]["scan_complete"])
        self.assertEqual(payload["summary"]["incomplete_files"], 0)

    def test_large_file_is_tolerated_by_default_and_gated_by_the_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "large.md", "production-ready " + ("x" * 128))
            tolerant = run_scanner(tmp, "--json-v2", "--max-file-bytes", "16")
            gated = run_scanner(tmp, "--json-v2", "--max-file-bytes", "16", "--fail-on-incomplete")
            quiet = run_scanner(
                tmp, "--max-file-bytes", "16", "--fail-on-incomplete", "--quiet"
            )
        payload = json.loads(tolerant.stdout)
        self.assertEqual(tolerant.returncode, 0, tolerant.stderr)
        self.assertFalse(payload["summary"]["scan_complete"])
        self.assertEqual(payload["summary"]["incomplete_files"], 1)
        self.assertEqual(gated.returncode, 3, gated.stderr)
        self.assertEqual(quiet.returncode, 3)
        self.assertEqual(quiet.stderr, "")

    def test_unreadable_file_is_gated_by_the_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "locked.md", "# doc\n")
            try:
                path.chmod(0o000)
            except (OSError, NotImplementedError):
                self.skipTest("cannot drop read permission here")
            readable_anyway = os.access(str(path), os.R_OK)
            try:
                if readable_anyway:
                    self.skipTest("this account can read a mode 000 file")
                proc = run_scanner(tmp, "--json-v2", "--fail-on-incomplete")
                payload = json.loads(proc.stdout)
            finally:
                path.chmod(0o644)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertEqual(payload["summary"]["files_unreadable"], 1)
        self.assertFalse(payload["summary"]["scan_complete"])

    def test_incomplete_coverage_outranks_a_finding_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "claim.md", "This tool is production-ready.\n")
            write(tmp, "large.md", "filler " + ("x" * 4096))
            both = run_scanner(
                tmp, "--max-file-bytes", "64", "--fail-on-block", "--fail-on-incomplete"
            )
            gate_only = run_scanner(tmp, "--max-file-bytes", "64", "--fail-on-block")
        self.assertEqual(both.returncode, 3, both.stderr)
        self.assertEqual(gate_only.returncode, 2, gate_only.stderr)


class ScannerTests(unittest.TestCase):
    def test_unquoted_claim_found_and_fails_on_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "README.md", "# tool\n\nThis tool is production-ready and battle-tested.\n")
            proc = run_scanner(tmp, "--fail-on-block")
        self.assertEqual(proc.returncode, 2)
        codes = {f["code"] for f in findings_of(proc)}
        self.assertIn("D2", codes)

    def test_json_v1_shape_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "README.md", "Production-ready.\n")
            proc = run_scanner(tmp)
        (finding,) = findings_of(proc)
        self.assertEqual(
            set(finding), {"path", "line", "code", "severity", "message", "excerpt"}
        )

    def test_json_v2_reports_multiple_findings_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "README.md",
                "A production-ready, robust, revolutionary tool using a generated image.\n",
            )
            proc = run_scanner(tmp, "--json-v2", "--max-findings", "2")
            again = run_scanner(tmp, "--json-v2", "--max-findings", "2")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(len(payload["findings"]), 2)
        self.assertGreaterEqual(payload["summary"]["total_findings"], 4)
        self.assertEqual(payload["summary"]["suppressed_findings"], 0)
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
            cases = {
                "block.md": ("production-ready\n", {"block": 2, "trim": 2, "flag": 2}),
                "trim.md": ("A robust tool.\n", {"block": 0, "trim": 2, "flag": 2}),
                "flag.md": ("A generated image.\n", {"block": 0, "trim": 0, "flag": 2}),
            }
            for filename, (text, expected) in cases.items():
                path = write(tmp, filename, text)
                for threshold, returncode in expected.items():
                    with self.subTest(filename=filename, threshold=threshold):
                        proc = run_scanner(str(path), "--fail-on", threshold)
                        self.assertEqual(proc.returncode, returncode, proc.stderr)

    def test_max_file_bytes_skips_content_and_reports_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "large.md", "production-ready " + ("x" * 128))
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
            write(
                tmp,
                "docs.md",
                '# banned words\n\n- "production-ready"\n- `battle-tested`\n'
                "- flag phrases like 'tests pass' in reviews\n",
            )
            proc = run_scanner(tmp, "--fail-on-block")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(findings_of(proc), [])

    def test_match_inside_string_literal_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "rules.py",
                'PATTERN = re.compile(r"\\b(production[- ]ready|battle[- ]tested)\\b")\n',
            )
            proc = run_scanner(tmp)
        self.assertEqual(findings_of(proc), [])

    def test_markdown_fence_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "example.md", "# doc\n\n```text\nAll tests passed. Enterprise-grade quality.\n```\n")
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
            write(Path(tmp, "vendor"), "x.md", "Battle-tested framework.\n")
            proc = run_scanner(tmp, "--exclude", "vendor/*")
            self.assertEqual(findings_of(proc), [])

    def test_disposable_filename_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "IMPLEMENTATION.md", "I changed things.\n")
            proc = run_scanner(tmp, "--fail-on-block")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("D1", {f["code"] for f in findings_of(proc)})

    def test_rules_option_replaces_the_bundled_registry(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            registry = write(
                home, "rules.json", json.dumps({"schema_version": 1, "rules": [ZEBRA_RULE]})
            )
            write(tmp, "doc.md", "A zebra. Production-ready.\n")
            proc = run_scanner(tmp, "--rules", str(registry))
            missing = run_scanner(tmp, "--rules", str(Path(home, "missing.json")))
            broken = run_scanner(tmp, "--rules", str(write(home, "broken.json", "{")))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual({f["code"] for f in findings_of(proc)}, {"T1"})
        for failed in (missing, broken):
            self.assertEqual(failed.returncode, 1)
            self.assertIn("Invalid anti-slop rule registry", failed.stderr)

    def test_structurally_invalid_registries_exit_1_without_a_traceback(self):
        broken = {
            "bad scopes": {"schema_version": 1, "rules": [dict(ZEBRA_RULE, scopes=[["repository"]])]},
            "kind mismatch": {"schema_version": 1, "rules": [dict(ZEBRA_RULE, filenames=["X.md"])]},
            "bad schema version": {"schema_version": 9, "rules": [ZEBRA_RULE]},
            "duplicate ids": {"schema_version": 1, "rules": [ZEBRA_RULE, ZEBRA_RULE]},
            "bad regex": {"schema_version": 1, "rules": [dict(ZEBRA_RULE, pattern="(")]},
        }
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as home:
            write(tmp, "doc.md", "A zebra.\n")
            for label, payload in broken.items():
                with self.subTest(label=label):
                    registry = write(home, "rules.json", json.dumps(payload))
                    proc = run_scanner(tmp, "--rules", str(registry))
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertIn("Invalid anti-slop rule registry", proc.stderr)
                    self.assertNotIn("Traceback", proc.stderr)

    def test_next_line_directive_suppresses_only_the_target_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "doc.md",
                "<!-- anti-slop-ignore-next-line S2-verification-claim -- describes the CI rule -->\n"
                "All tests passed.\n"
                "All tests passed.\n",
            )
            proc = run_scanner(tmp, "--json-v2", "--fail-on-block")
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertEqual([f["line"] for f in payload["findings"]], [3])
        self.assertEqual(payload["summary"]["total_findings"], 1)
        self.assertEqual(payload["summary"]["suppressed_findings"], 1)
        self.assertNotIn("directive ignored", proc.stderr)

    def test_file_directive_covers_filename_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "SUMMARY.md",
                "<!-- anti-slop-ignore-file D7-summary-file -- mdBook table of contents -->\n\n"
                "- [Intro](intro.md)\n",
            )
            proc = run_scanner(tmp, "--json-v2", "--fail-on-block")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["summary"]["suppressed_findings"], 1)

    def test_invalid_directives_are_reported_and_suppress_nothing(self):
        lines = [
            "<!-- anti-slop-ignore-next-line Nope-rule -- unknown id -->",
            "Production-ready.",
            "<!-- anti-slop-ignore-next-line D2-maturity-claim -->",
            "Production-ready.",
            "<!-- anti-slop-ignore-next-line D2-maturity-claim -- unterminated",
            "Production-ready.",
        ]
        lines += [""] * 5
        lines.append("<!-- anti-slop-ignore-file D2-maturity-claim -- too late -->")
        self.assertEqual(len(lines), 12)
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "doc.md", "\n".join(lines) + "\n")
            proc = run_scanner(tmp, "--json-v2")
            quiet = run_scanner(tmp, "--json-v2", "--quiet")
        payload = json.loads(proc.stdout)
        self.assertEqual([f["line"] for f in payload["findings"]], [2, 4, 6])
        self.assertEqual(payload["summary"]["suppressed_findings"], 0)
        self.assertEqual(proc.stderr.count("anti-slop directive ignored"), 4)
        self.assertIn("doc.md:12:", proc.stderr)
        self.assertNotIn("directive ignored", quiet.stderr)
        self.assertEqual(quiet.stdout, proc.stdout)

    def test_html_directive_must_own_the_whole_line(self):
        lines = [
            "<!-- anti-slop-ignore-next-line S3-attention-bait -- note --> All tests passed. <!-- -->",
            "<!-- anti-slop-ignore-file S3-attention-bait -- note --> All tests passed.",
            "All tests passed. <!-- anti-slop-ignore-file S2-verification-claim -- trailing -->",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "doc.md", "\n".join(lines) + "\n")
            proc = run_scanner(tmp, "--json-v2")
        payload = json.loads(proc.stdout)
        self.assertEqual(
            [(f["rule_id"], f["line"]) for f in payload["findings"]],
            [("S2-verification-claim", 1), ("S2-verification-claim", 2), ("S2-verification-claim", 3)],
        )
        self.assertEqual(payload["summary"]["suppressed_findings"], 0)
        self.assertEqual(proc.stderr.count("must be the whole line"), 2)

    def test_html_directive_tolerates_trailing_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "doc.md",
                "<!-- anti-slop-ignore-next-line S2-verification-claim -- quotes the policy -->   \n"
                "All tests passed.\n",
            )
            proc = run_scanner(tmp, "--json-v2")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["summary"]["suppressed_findings"], 1)
        self.assertEqual(proc.stderr, "")

    def test_json_v2_reports_every_directive_with_its_reason_and_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "doc.md",
                "<!-- anti-slop-ignore-file S2-verification-claim -- quotes the CI policy -->\n"
                "<!-- anti-slop-ignore-next-line S2-verification-claim -- the same claim -->\n"
                "All tests passed.\n"
                "<!-- anti-slop-ignore-next-line S3-attention-bait -- never matches -->\n"
                "plain prose\n",
            )
            proc = run_scanner(tmp, "--json-v2")
            gated = run_scanner(tmp, "--fail-on-unused-suppression", "--quiet")
            ungated = run_scanner(tmp, "--quiet")
        payload = json.loads(proc.stdout)
        rows = payload["suppressions"]
        self.assertEqual(
            [
                (r["rule_id"], r["scope"], r["directive_line"], r["target_line"],
                 r["matched_findings"], r["unused"])
                for r in rows
            ],
            [
                ("S2-verification-claim", "file", 1, None, 0, False),
                ("S2-verification-claim", "next-line", 2, 3, 1, False),
                ("S3-attention-bait", "next-line", 4, 5, 0, True),
            ],
        )
        self.assertEqual(rows[0]["reason"], "quotes the CI policy")
        self.assertEqual(rows[0]["path"], "doc.md")
        # The overlapping directives cover one finding between them, counted once.
        self.assertEqual(payload["summary"]["suppressed_findings"], 1)
        self.assertEqual(payload["summary"]["total_findings"], 0)
        self.assertEqual(payload["findings"], [])
        self.assertIn("matched no finding", proc.stderr)
        self.assertEqual(gated.returncode, 2, gated.stderr)
        self.assertEqual(gated.stderr, "")
        self.assertEqual(ungated.returncode, 0, ungated.stderr)

    def test_unused_gate_passes_when_every_directive_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "doc.md",
                "<!-- anti-slop-ignore-next-line S2-verification-claim -- quoted policy -->\n"
                "All tests passed.\n",
            )
            proc = run_scanner(tmp, "--json-v2", "--fail-on-unused-suppression")
        payload = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual([r["unused"] for r in payload["suppressions"]], [False])
        self.assertEqual(payload["summary"]["suppressed_findings"], 1)

    def test_json_v1_is_unaffected_by_suppression_reporting(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "doc.md",
                "<!-- anti-slop-ignore-next-line S2-verification-claim -- quoted policy -->\n"
                "All tests passed.\n"
                "This tool is production-ready.\n",
            )
            proc = run_scanner(tmp, "--json")
        findings = findings_of(proc)
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            set(findings[0]), {"path", "line", "code", "severity", "message", "excerpt"}
        )
        self.assertEqual(findings[0]["line"], 3)

    def test_directive_inside_fence_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "doc.md",
                "```md\n<!-- anti-slop-ignore-next-line D2-maturity-claim -- example -->\n```\n"
                "Production-ready.\n",
            )
            proc = run_scanner(tmp, "--json-v2")
        payload = json.loads(proc.stdout)
        self.assertEqual([f["line"] for f in payload["findings"]], [4])
        self.assertEqual(payload["summary"]["suppressed_findings"], 0)
        self.assertEqual(proc.stderr, "")

    def test_directive_line_with_trigger_words_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(
                tmp,
                "doc.md",
                "<!-- anti-slop-ignore-next-line S2-verification-claim -- the phrase tests pass below is quoted from the CI policy -->\n"
                "All tests passed.\n",
            )
            proc = run_scanner(tmp, "--json-v2")
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["summary"]["suppressed_findings"], 1)

    def test_suppression_applies_before_thresholds_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(
                tmp,
                "doc.md",
                "<!-- anti-slop-ignore-next-line D2-maturity-claim -- vendor wording -->\n"
                "Production-ready.\n"
                "A robust tool.\n"
                "A seamless tool.\n",
            )
            gate = run_scanner(str(path), "--fail-on-block")
            truncated = run_scanner(str(path), "--json-v2", "--max-findings", "1")
        self.assertEqual(gate.returncode, 0, gate.stdout)
        payload = json.loads(truncated.stdout)
        self.assertEqual([f["line"] for f in payload["findings"]], [3])
        self.assertEqual(payload["omitted_findings"], 1)
        self.assertEqual(payload["summary"]["total_findings"], 2)
        self.assertEqual(payload["summary"]["suppressed_findings"], 1)

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
