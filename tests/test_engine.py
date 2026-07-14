"""Tests for the shared deterministic anti-slop engine."""

import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent / "anti-slop"
sys.path.insert(0, str(SKILL_ROOT))

from lib.anti_slop_engine import (  # noqa: E402
    RegistryError,
    fails_at,
    filename_findings,
    load_rules,
    scan_text,
)


class RegistryTests(unittest.TestCase):
    def test_registry_is_valid_and_ids_are_unique(self):
        rules = load_rules()
        self.assertGreaterEqual(len(rules), 15)
        self.assertEqual(len({rule.rule_id for rule in rules}), len(rules))
        self.assertEqual({rule.decision for rule in rules}, {"BLOCK", "TRIM", "FLAG"})

    def test_invalid_registry_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "rules.json")
            path.write_text(json.dumps({"schema_version": 1, "rules": []}), encoding="utf-8")
            with self.assertRaises(RegistryError):
                load_rules(path)


class DetectionTests(unittest.TestCase):
    def scan_repo(self, text, markdown=True):
        return scan_text(
            text,
            path="README.md",
            scope="repository",
            markdown=markdown,
        )

    def test_reports_multiple_rules_on_one_line(self):
        findings = self.scan_repo("Production-ready; all tests passed.\n")
        self.assertEqual({finding.rule_id for finding in findings}, {
            "D2-maturity-claim",
            "S2-verification-claim",
        })

    def test_apostrophe_does_not_hide_claim(self):
        findings = self.scan_repo("It's production-ready.\n")
        self.assertIn("D2-maturity-claim", {finding.rule_id for finding in findings})

    def test_quoted_and_backticked_mentions_are_ignored(self):
        findings = self.scan_repo(
            "Avoid the phrase 'production-ready' and the token `all tests passed`.\n"
        )
        self.assertEqual(findings, [])

    def test_markdown_fences_are_ignored(self):
        findings = self.scan_repo(
            "Before\n   ```text\nProduction-ready. All tests passed.\n   ```\nAfter\n"
        )
        self.assertEqual(findings, [])

    def test_unclosed_markdown_fence_masks_the_remainder(self):
        findings = self.scan_repo("```text\nProduction-ready.\n")
        self.assertEqual(findings, [])

    def test_response_scope_uses_response_and_shared_rules(self):
        findings = scan_text(
            "Great question! This is robust.\n",
            path="<assistant-response>",
            scope="response",
            markdown=True,
        )
        by_id = {finding.rule_id: finding for finding in findings}
        self.assertEqual(by_id["C3-sycophantic-opener"].severity, "TRIM")
        self.assertEqual(by_id["D2-polish-word"].severity, "TRIM")

    def test_filename_rule_has_layered_severity(self):
        finding = filename_findings("IMPLEMENTATION.md", path="IMPLEMENTATION.md")[0]
        self.assertEqual(finding.impact, "critical")
        self.assertEqual(finding.severity, "BLOCK")

    def test_legacy_and_detailed_json_shapes(self):
        finding = self.scan_repo("Production-ready.\n")[0]
        self.assertEqual(set(finding.legacy_dict()), {
            "path", "line", "code", "severity", "message", "excerpt",
        })
        self.assertIn("rule_id", finding.detailed_dict())
        self.assertIn("impact", finding.detailed_dict())
        self.assertIn("fix", finding.detailed_dict())

    def test_threshold_includes_stricter_decisions(self):
        block = self.scan_repo("Production-ready.\n")
        trim = self.scan_repo("This is robust.\n")
        flag = self.scan_repo("Generated image provenance is recorded elsewhere.\n")
        self.assertTrue(fails_at(block, "BLOCK"))
        self.assertTrue(fails_at(block, "TRIM"))
        self.assertFalse(fails_at(trim, "BLOCK"))
        self.assertTrue(fails_at(trim, "TRIM"))
        self.assertTrue(fails_at(flag, "FLAG"))


if __name__ == "__main__":
    unittest.main()
