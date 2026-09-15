"""Run the deterministic rule corpus through the shared engine."""

import json
import sys
import unittest
from pathlib import Path, PurePosixPath


SKILL_ROOT = Path(__file__).resolve().parent.parent / "anti-slop"
sys.path.insert(0, str(SKILL_ROOT))

from lib.anti_slop_engine import (  # noqa: E402
    VALID_DECISIONS,
    VALID_SCOPES,
    filename_findings,
    load_rules,
    scan_text,
)

CORPUS = SKILL_ROOT / "evals" / "rule-corpus.json"
REQUIRED_KEYS = {"id", "path", "scope", "markdown", "text", "expect", "must_not_find"}


def load_cases():
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    return payload, payload["cases"]


def run_case(case, rules):
    path = case["path"]
    findings = filename_findings(
        PurePosixPath(path).name, path=path, scope=case["scope"], rules=rules
    )
    findings = findings + scan_text(
        case["text"],
        path=path,
        scope=case["scope"],
        markdown=case["markdown"],
        rules=rules,
    )
    return sorted((finding.rule_id, finding.line, finding.severity) for finding in findings)


def expected_of(case):
    return sorted((item["rule_id"], item["line"], item["decision"]) for item in case["expect"])


class CorpusSchemaTests(unittest.TestCase):
    def test_schema(self):
        payload, cases = load_cases()
        rule_ids = {rule.rule_id for rule in load_rules()}

        self.assertEqual(payload["schema_version"], 1)
        self.assertIsInstance(cases, list)
        self.assertTrue(cases)

        seen = set()
        for case in cases:
            with self.subTest(case=case.get("id")):
                self.assertTrue(REQUIRED_KEYS <= set(case), f"missing keys: {REQUIRED_KEYS - set(case)}")
                self.assertIsInstance(case["id"], str)
                self.assertTrue(case["id"].strip())
                self.assertNotIn(case["id"], seen)
                seen.add(case["id"])
                self.assertIsInstance(case["path"], str)
                self.assertTrue(case["path"])
                self.assertIn(case["scope"], VALID_SCOPES)
                self.assertIsInstance(case["markdown"], bool)
                self.assertIsInstance(case["text"], str)
                self.assertIsInstance(case["expect"], list)
                self.assertIsInstance(case["must_not_find"], list)
                expected_ids = set()
                for item in case["expect"]:
                    self.assertIn(item["rule_id"], rule_ids)
                    self.assertIsInstance(item["line"], int)
                    self.assertGreaterEqual(item["line"], 1)
                    self.assertIn(item["decision"], VALID_DECISIONS)
                    expected_ids.add(item["rule_id"])
                for rule_id in case["must_not_find"]:
                    self.assertIn(rule_id, rule_ids)
                self.assertFalse(
                    expected_ids & set(case["must_not_find"]),
                    "a rule cannot be both expected and forbidden in one case",
                )
                if not case["expect"]:
                    self.assertTrue(case["must_not_find"], "negative cases must name the rules they exclude")


class CorpusCaseTests(unittest.TestCase):
    def test_cases_match_exactly(self):
        _, cases = load_cases()
        rules = load_rules()
        for case in cases:
            with self.subTest(case=case["id"]):
                actual = run_case(case, rules)
                self.assertEqual(actual, expected_of(case))
                for rule_id in case["must_not_find"]:
                    self.assertNotIn(rule_id, {item[0] for item in actual})

    def test_every_rule_has_positive_and_negative_coverage(self):
        _, cases = load_cases()
        rule_ids = {rule.rule_id for rule in load_rules()}
        expected = {item["rule_id"] for case in cases for item in case["expect"]}
        forbidden = {rule_id for case in cases for rule_id in case["must_not_find"]}
        self.assertEqual(rule_ids - expected, set(), "rules without a positive case")
        self.assertEqual(rule_ids - forbidden, set(), "rules without a negative case")


if __name__ == "__main__":
    unittest.main()
