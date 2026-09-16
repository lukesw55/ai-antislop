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


BASE_RULE = {
    "id": "T1-test",
    "code": "T1",
    "impact": "minor",
    "decision": "FLAG",
    "scopes": ["repository"],
    "kind": "regex",
    "pattern": "\\bslop\\b",
    "message": "test rule",
    "fix": "remove it",
}


def write_registry(directory, *rules):
    path = Path(directory, "rules.json")
    path.write_text(json.dumps({"schema_version": 1, "rules": list(rules)}), encoding="utf-8")
    return path


def rule(**overrides):
    merged = dict(BASE_RULE)
    merged.update(overrides)
    for key, value in list(merged.items()):
        if value is None:
            del merged[key]
    return merged


class RegistryTests(unittest.TestCase):
    def test_registry_is_valid_and_ids_are_unique(self):
        rules = load_rules()
        self.assertGreaterEqual(len(rules), 15)
        self.assertEqual(len({rule.rule_id for rule in rules}), len(rules))
        self.assertEqual({rule.decision for rule in rules}, {"BLOCK", "TRIM", "FLAG"})
        self.assertEqual({rule.kind for rule in rules}, {"filename", "regex", "sequence"})

    def test_invalid_registry_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "rules.json")
            path.write_text(json.dumps({"schema_version": 1, "rules": []}), encoding="utf-8")
            with self.assertRaises(RegistryError):
                load_rules(path)

    def test_unknown_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_registry(tmp, rule(unless_preceeded_by=["not"]))
            with self.assertRaisesRegex(RegistryError, "unknown keys"):
                load_rules(path)

    def test_sequence_rule_validation(self):
        base = rule(kind="sequence", pattern=None, line_pattern="^- ", min_consecutive=3)
        invalid = {
            "multiline flag": rule(**dict(base, flags=["MULTILINE"])),
            "min_consecutive below two": rule(**dict(base, min_consecutive=1)),
            "boolean min_consecutive": rule(**dict(base, min_consecutive=True)),
            "missing min_consecutive": rule(**dict(base, min_consecutive=None)),
            "missing line_pattern": rule(**dict(base, line_pattern=None)),
        }
        for label, raw in invalid.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RegistryError):
                    load_rules(write_registry(tmp, raw))
        with tempfile.TemporaryDirectory() as tmp:
            rules = load_rules(write_registry(tmp, base))
        self.assertEqual(rules[0].kind, "sequence")
        self.assertEqual(rules[0].min_consecutive, 3)

    def test_exclusion_validation(self):
        invalid = {
            "filename rule": rule(
                kind="filename", pattern=None, filenames=["X.md"], unless_preceded_by=["not"]
            ),
            "empty list": rule(unless_preceded_by=[]),
            "non-string item": rule(unless_followed_by=[1]),
            "bad regex": rule(unless_followed_by=["("]),
            "empty object": rule(unless_followed_by={}),
            "object with empty key": rule(unless_followed_by={"": ["x"]}),
            "object with non-list value": rule(unless_followed_by={"magic": "numbers"}),
            "object with bad key regex": rule(unless_followed_by={"(": ["x"]}),
        }
        for label, raw in invalid.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RegistryError):
                    load_rules(write_registry(tmp, raw))

    def test_object_form_exclusion_targets_one_alternative(self):
        custom = rule(pattern="\\b(alpha|beta)\\b", unless_followed_by={"alpha": ["one"]})
        with tempfile.TemporaryDirectory() as tmp:
            rules = load_rules(write_registry(tmp, custom))
        findings = scan_text(
            "alpha one\nbeta one\nalpha two\n",
            path="x.md",
            scope="repository",
            markdown=False,
            rules=rules,
        )
        self.assertEqual([finding.line for finding in findings], [2, 3])


class DetectionTests(unittest.TestCase):
    def scan_repo(self, text, markdown=True):
        return scan_text(
            text,
            path="README.md",
            scope="repository",
            markdown=markdown,
        )

    def scan_response(self, text):
        return scan_text(
            text,
            path="<assistant-response>",
            scope="response",
            markdown=True,
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
        findings = self.scan_response("Great question! This is robust.\n")
        by_id = {finding.rule_id: finding for finding in findings}
        self.assertEqual(by_id["C3-sycophantic-opener"].severity, "TRIM")
        self.assertEqual(by_id["D2-polish-word"].severity, "TRIM")

    def test_leading_blank_lines_attribute_to_the_content_line(self):
        findings = self.scan_response("\n\nGreat question! Here it is.\n")
        c3 = [finding for finding in findings if finding.rule_id == "C3-sycophantic-opener"]
        self.assertEqual([(finding.line, finding.excerpt) for finding in c3], [
            (3, "Great question! Here it is."),
        ])

    def test_crlf_heading_attributes_to_the_heading_line(self):
        findings = self.scan_repo("# Tool\r\n\r\n## Overview\r\n\r\nText.\r\n")
        self.assertEqual(
            [(finding.rule_id, finding.line, finding.excerpt) for finding in findings],
            [("S1-template-heading", 3, "## Overview")],
        )

    def test_label_colon_bullets_need_three_consecutive_lines(self):
        two = self.scan_repo("Intro\n\n- **Theme:** one\n- **Voice:** two\n")
        self.assertEqual(two, [])
        three = self.scan_repo("Intro\n\n- **Theme:** one\n- **Voice:** two\n- **Tone:** three\n")
        self.assertEqual(
            [(finding.rule_id, finding.line, finding.excerpt) for finding in three],
            [("S1-label-colon-bullet", 3, "- **Theme:** one")],
        )

    def test_imperative_instructions_are_excluded_but_assertions_are_not(self):
        excluded = (
            "Confirm that tests pass before merging.\n",
            "Verify that all tests pass before pushing.\n",
            "Run lint. Then ensure all tests pass.\n",
            "Please ensure all tests pass.\n",
            "- Ensure all tests pass.\n",
            "1. Verify that the build passes.\n",
            "**Ensure** all tests pass.\n",
        )
        for text in excluded:
            with self.subTest(text=text):
                self.assertEqual(self.scan_repo(text), [])
        asserted = (
            "I confirm that all tests pass.\n",
            "I verify that tests pass.\n",
            "We confirm that the build passes.\n",
            "I ensure that all tests pass.\n",
            "The maintainer confirms that tests pass.\n",
        )
        for text in asserted:
            with self.subTest(text=text):
                self.assertEqual(
                    [finding.rule_id for finding in self.scan_repo(text)],
                    ["S2-verification-claim"],
                )

    def test_conditional_and_negated_claims_are_excluded(self):
        for text in (
            "If tests pass, commit:\n",
            "When **tests pass**, merge.\n",
            "If all tests pass, commit.\n",
            "When the build passes, deploy.\n",
            "Ensure all tests pass before pushing.\n",
            "This is not production-ready.\n",
            "x = 42  # magic number\n",
            "Weights get a 10x multiplier.\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.scan_repo(text, markdown=False), [])
        for text in (
            "I verified that tests pass.\n",
            "The build passes on main.\n",
            "Now 10x faster.\n",
            "This is magic!\n",
            "Our launch delivered shocking numbers.\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(len(self.scan_repo(text, markdown=False)), 1)

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
