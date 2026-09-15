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
    Suppression,
    apply_suppressions,
    fails_at,
    filename_findings,
    load_rules,
    parse_directives,
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


class DirectiveTests(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules()

    def parse(self, text, markdown=False):
        return parse_directives(text, self.rules, markdown=markdown)

    def test_parses_all_three_comment_forms(self):
        text = (
            "<!-- anti-slop-ignore-file D7-summary-file -- mdBook index -->\n"
            "# anti-slop-ignore-next-line S2-verification-claim -- conditional\n"
            "if tests pass: ok\n"
            "  // anti-slop-ignore-next-line S3-attention-bait -- product name\n"
            "Magic Mouse\n"
        )
        suppressions, problems = self.parse(text)
        self.assertEqual(problems, [])
        self.assertEqual(
            [(s.rule_id, s.scope, s.directive_line, s.target_line) for s in suppressions],
            [
                ("D7-summary-file", "file", 1, None),
                ("S2-verification-claim", "next-line", 2, 3),
                ("S3-attention-bait", "next-line", 4, 5),
            ],
        )
        self.assertEqual(suppressions[0].reason, "mdBook index")

    def test_non_directive_lines_are_left_alone(self):
        for text in (
            "code = 1  # anti-slop-ignore-next-line S2-verification-claim -- trailing\nx\n",
            "# anti-slop-ignore-next-lines S2-verification-claim -- plural\nx\n",
            "# anti-slop-ignore-file-wide S2-verification-claim -- suffix\nx\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), ([], []))

    def test_malformed_and_misplaced_directives_are_problems(self):
        cases = {
            "unterminated html": (
                "<!-- anti-slop-ignore-next-line S2-verification-claim -- x\nAll tests passed.\n",
                "must end with -->",
            ),
            "missing reason": (
                "# anti-slop-ignore-next-line S2-verification-claim\nx\n",
                "expected",
            ),
            "unknown rule": (
                "# anti-slop-ignore-next-line Nope -- x\nx\n",
                "unknown rule id",
            ),
            "no following line": (
                "x\n# anti-slop-ignore-next-line S2-verification-claim -- x\n",
                "no following line",
            ),
            "file directive too late": (
                "\n" * 10 + "# anti-slop-ignore-file S2-verification-claim -- late\nx\n",
                "first 10 lines",
            ),
        }
        for label, (text, fragment) in cases.items():
            with self.subTest(label=label):
                suppressions, problems = self.parse(text)
                self.assertEqual(suppressions, [])
                self.assertEqual(len(problems), 1)
                self.assertIn(fragment, problems[0].reason)

    def test_fenced_directives_are_not_recognized_in_markdown(self):
        text = "```\n# anti-slop-ignore-file D2-maturity-claim -- example\n```\nProduction-ready.\n"
        self.assertEqual(self.parse(text, markdown=True), ([], []))
        suppressions, _ = self.parse(text, markdown=False)
        self.assertEqual([s.scope for s in suppressions], ["file"])

    def test_apply_suppressions_uses_exact_rule_and_line(self):
        findings = scan_text(
            "Production-ready.\nProduction-ready.\nAll tests passed.\n",
            path="x.md",
            scope="repository",
            markdown=True,
        )
        suppressions = [
            Suppression("D2-maturity-claim", "next-line", 0, 2, "vendor wording"),
            Suppression("S2-verification-claim", "file", 0, None, "quoted policy"),
        ]
        active, suppressed = apply_suppressions(findings, suppressions)
        self.assertEqual([(f.rule_id, f.line) for f in active], [("D2-maturity-claim", 1)])
        self.assertEqual(
            [(f.rule_id, f.line) for f in suppressed],
            [("D2-maturity-claim", 2), ("S2-verification-claim", 3)],
        )

    def test_skip_lines_drops_findings_on_those_lines(self):
        regex = scan_text(
            "Production-ready.\nProduction-ready.\n",
            path="x.md",
            scope="repository",
            markdown=True,
            skip_lines={1},
        )
        self.assertEqual([f.line for f in regex], [2])
        sequence = scan_text(
            "- **Alpha:** 1\n- **Beta:** 2\n- **Gamma:** 3\n",
            path="x.md",
            scope="repository",
            markdown=True,
            skip_lines={1},
        )
        self.assertEqual(sequence, [])


if __name__ == "__main__":
    unittest.main()
