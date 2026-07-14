import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "anti-slop"
LIB_DIR = SKILL_DIR / "lib"
sys.path.insert(0, str(LIB_DIR))

from anti_slop_engine import RegistryError, load_rules  # noqa: E402


def parse_frontmatter(text: str):
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise AssertionError("SKILL.md must start with YAML frontmatter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise AssertionError("SKILL.md frontmatter is not closed") from exc

    values = {}
    for line in lines[1:closing]:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise AssertionError(f"unsupported frontmatter line: {line}")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values, "\n".join(lines[closing + 1 :]).lstrip()


class SkillContractTests(unittest.TestCase):
    def test_frontmatter_is_portable_and_matches_directory(self):
        metadata, body = parse_frontmatter((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))

        self.assertEqual({"name", "description"}, set(metadata))
        self.assertEqual(SKILL_DIR.name, metadata["name"])
        self.assertRegex(metadata["name"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertLessEqual(len(metadata["name"]), 64)
        self.assertTrue(metadata["description"])
        self.assertLessEqual(len(metadata["description"]), 1024)
        self.assertTrue(body.startswith("# "))

    def test_backticked_skill_paths_exist(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        paths = re.findall(
            r"`((?:references|rules|scripts|hooks)/[^`\s]+)`",
            text,
        )
        self.assertTrue(paths, "SKILL.md should route readers to bundled resources")
        missing = [path for path in paths if not (SKILL_DIR / path).exists()]
        self.assertEqual([], missing)

    def test_executable_registry_contract(self):
        try:
            rules = load_rules(SKILL_DIR / "rules" / "rules.json")
        except RegistryError as exc:
            self.fail(str(exc))

        self.assertGreater(len(rules), 0)
        self.assertEqual(len(rules), len({rule.rule_id for rule in rules}))
        self.assertTrue(any("repository" in rule.scopes for rule in rules))
        self.assertTrue(any("response" in rule.scopes for rule in rules))

    def test_eval_files_have_stable_case_ids(self):
        eval_dir = SKILL_DIR / "evals"
        cases = json.loads((eval_dir / "evals.json").read_text(encoding="utf-8"))
        self.assertIsInstance(cases, list)
        self.assertTrue(cases)
        seen = set()
        for case in cases:
            case_id = case.get("id") or case.get("name")
            self.assertIsInstance(case_id, str, "eval case without id/name")
            self.assertTrue(case_id.strip(), "empty eval case id/name")
            self.assertNotIn(case_id, seen, f"duplicate eval case id: {case_id}")
            seen.add(case_id)

        triggers = json.loads(
            (eval_dir / "trigger-queries.json").read_text(encoding="utf-8")
        )
        self.assertIsInstance(triggers, dict)
        for bucket in ("should_trigger", "should_not_trigger_or_keep_light"):
            queries = triggers.get(bucket)
            self.assertIsInstance(queries, list, f"{bucket} must be a list")
            self.assertTrue(queries, f"{bucket} must not be empty")
            self.assertTrue(
                all(isinstance(query, str) and query.strip() for query in queries),
                f"{bucket} must contain non-empty strings",
            )


if __name__ == "__main__":
    unittest.main()
