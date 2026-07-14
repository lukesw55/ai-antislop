"""Tests for anti-slop/scripts/sync_skill.py."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "anti-slop"
SYNC = SOURCE / "scripts" / "sync_skill.py"

SYNC_SPEC = importlib.util.spec_from_file_location("anti_slop_sync_skill_test", SYNC)
assert SYNC_SPEC is not None and SYNC_SPEC.loader is not None
SYNC_MODULE = importlib.util.module_from_spec(SYNC_SPEC)
sys.modules[SYNC_SPEC.name] = SYNC_MODULE
SYNC_SPEC.loader.exec_module(SYNC_MODULE)


def run_sync(*args, cwd=None, env_extra=None):
    env = dict(os.environ)
    env.pop("CODEX_HOME", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SYNC), *map(str, args)],
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


class SyncSkillTests(unittest.TestCase):
    def test_project_all_materializes_native_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = run_sync("--project", root)

            self.assertEqual(proc.returncode, 0, proc.stderr)
            agents = root / ".agents" / "skills" / "anti-slop"
            claude = root / ".claude" / "skills" / "anti-slop"
            cursor = root / ".cursor" / "rules" / "antislop.mdc"
            self.assertEqual(
                (agents / "SKILL.md").read_bytes(),
                (SOURCE / "SKILL.md").read_bytes(),
            )
            self.assertEqual(
                (claude / "SKILL.md").read_bytes(),
                (SOURCE / "SKILL.md").read_bytes(),
            )
            self.assertFalse((root / ".codex").exists())
            self.assertFalse(any(path.name == "__pycache__" for path in agents.rglob("*")))

            cursor_text = cursor.read_text(encoding="utf-8")
            self.assertTrue(cursor_text.startswith("---\ndescription: "))
            self.assertIn("\nalwaysApply: false\n---\n", cursor_text)
            self.assertIn(
                ".agents/skills/anti-slop/references/slop-taxonomy.md",
                cursor_text,
            )

    def test_project_legacy_targets_are_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = run_sync("--project", root, "--target", "codex-legacy")
            self.assertEqual(explicit.returncode, 0, explicit.stderr)
            legacy = root / ".codex" / "skills" / "anti-slop"
            self.assertTrue((legacy / "SKILL.md").is_file())
            self.assertFalse((root / ".agents").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            alias = run_sync(
                "--project", root, "--target", "agents", "--legacy-codex"
            )
            self.assertEqual(alias.returncode, 0, alias.stderr)
            self.assertTrue(
                (root / ".agents" / "skills" / "anti-slop" / "SKILL.md").is_file()
            )
            self.assertTrue(
                (root / ".codex" / "skills" / "anti-slop" / "SKILL.md").is_file()
            )

    def test_user_legacy_uses_codex_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "configured-codex"
            proc = run_sync(
                "--user",
                root / "home",
                "--target",
                "codex-legacy",
                env_extra={"CODEX_HOME": str(codex_home)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((codex_home / "skills" / "anti-slop" / "SKILL.md").is_file())
            self.assertFalse((root / "home" / ".codex").exists())

    def test_user_cursor_uses_agents_without_creating_a_user_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = run_sync("--user", root, "--target", "cursor")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(
                (root / ".agents" / "skills" / "anti-slop" / "SKILL.md").is_file()
            )
            self.assertFalse((root / ".cursor").exists())

    def test_cursor_body_only_omits_frontmatter_and_still_installs_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = run_sync(
                "--project",
                root,
                "--target",
                "cursor",
                "--cursor-body-only",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(
                (root / ".agents" / "skills" / "anti-slop" / "SKILL.md").is_file()
            )
            rule = (root / ".cursor" / "rules" / "antislop.mdc").read_text(
                encoding="utf-8"
            )
            self.assertTrue(rule.startswith("# Anti-slop\n"))
            self.assertNotIn("alwaysApply:", rule)
            self.assertIn(
                ".agents/skills/anti-slop/references/docs-patterns.md",
                rule,
            )

    def test_recognized_cursor_rule_variants_update_without_force(self):
        variants = (
            ("# Anti-slop\n\nOld body-only rule.\n", ()),
            (
                "---\ndescription: old\nalwaysApply: false\n---\n\n"
                "# Anti-slop\n\nOld frontmatter rule.\n",
                ("--cursor-body-only",),
            ),
        )
        for existing, extra_args in variants:
            with self.subTest(body_only=bool(extra_args)):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    cursor = root / ".cursor" / "rules" / "antislop.mdc"
                    cursor.parent.mkdir(parents=True)
                    cursor.write_text(existing, encoding="utf-8")

                    proc = run_sync(
                        "--project", root, "--target", "cursor", *extra_args
                    )

                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    updated = cursor.read_text(encoding="utf-8")
                    self.assertNotIn("Old ", updated)
                    if extra_args:
                        self.assertTrue(updated.startswith("# Anti-slop\n"))
                    else:
                        self.assertTrue(updated.startswith("---\ndescription: "))

    def test_foreign_cursor_rule_requires_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cursor = root / ".cursor" / "rules" / "antislop.mdc"
            cursor.parent.mkdir(parents=True)
            foreign = "# Foreign rule\n\nKeep this content.\n"
            cursor.write_text(foreign, encoding="utf-8")

            refused = run_sync("--project", root, "--target", "cursor")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("refusing to replace", refused.stderr)
            self.assertEqual(cursor.read_text(encoding="utf-8"), foreign)
            self.assertFalse((root / ".agents").exists())

            forced = run_sync(
                "--project", root, "--target", "cursor", "--force"
            )
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertTrue(
                cursor.read_text(encoding="utf-8").startswith("---\ndescription: ")
            )

    def test_dry_run_reports_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = run_sync("--project", root, "--dry-run")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("would sync", proc.stdout)
            self.assertFalse((root / ".agents").exists())
            self.assertFalse((root / ".claude").exists())
            self.assertFalse((root / ".cursor").exists())

    def test_check_detects_drift_without_repairing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = root / ".agents" / "skills" / "anti-slop"
            first = run_sync("--project", root, "--target", "agents")
            self.assertEqual(first.returncode, 0, first.stderr)

            clean = run_sync("--project", root, "--target", "agents", "--check")
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

            marker = installed / "local-change.txt"
            marker.write_text("drift\n", encoding="utf-8")
            drift = run_sync("--project", root, "--target", "agents", "--check")
            self.assertEqual(drift.returncode, 1, drift.stdout + drift.stderr)
            self.assertIn("drift .agents", drift.stdout)
            self.assertTrue(marker.is_file())

    def test_second_sync_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = run_sync("--project", root, "--target", "agents")
            second = run_sync("--project", root, "--target", "agents")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout.strip(), "ok")

    def test_refuses_unrecognized_skill_destination_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / ".agents" / "skills" / "anti-slop"
            destination.mkdir(parents=True)
            foreign = destination / "SKILL.md"
            foreign.write_text(
                "---\nname: another-skill\ndescription: unrelated\n---\n",
                encoding="utf-8",
            )

            refused = run_sync("--project", root, "--target", "agents")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("refusing to replace", refused.stderr)
            self.assertIn("another-skill", foreign.read_text(encoding="utf-8"))

            forced = run_sync(
                "--project", root, "--target", "agents", "--force"
            )
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertEqual(foreign.read_bytes(), (SOURCE / "SKILL.md").read_bytes())

    def test_tree_update_rolls_back_when_second_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination_parent = root / "destinations"
            destination = destination_parent / "anti-slop"
            source.mkdir()
            destination.mkdir(parents=True)
            (source / "SKILL.md").write_text("new\n", encoding="utf-8")
            (source / "new.txt").write_text("new\n", encoding="utf-8")
            (destination / "SKILL.md").write_text("old\n", encoding="utf-8")
            (destination / "old.txt").write_text("old\n", encoding="utf-8")

            real_replace = os.replace
            replace_calls = []

            def fail_second_replace(source_path, destination_path):
                replace_calls.append((source_path, destination_path))
                if len(replace_calls) == 2:
                    raise OSError("injected replace failure")
                return real_replace(source_path, destination_path)

            with mock.patch.object(
                SYNC_MODULE.os,
                "replace",
                side_effect=fail_second_replace,
            ):
                with self.assertRaises(OSError):
                    SYNC_MODULE._write_tree(source, destination)

            self.assertEqual(len(replace_calls), 3)
            self.assertEqual(
                (destination / "SKILL.md").read_text(encoding="utf-8"),
                "old\n",
            )
            self.assertTrue((destination / "old.txt").is_file())
            self.assertFalse((destination / "new.txt").exists())
            self.assertEqual(list(destination_parent.iterdir()), [destination])

    def test_project_without_path_uses_current_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = run_sync(
                "--project", "--target", "agents", cwd=root
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(
                (root / ".agents" / "skills" / "anti-slop" / "SKILL.md").is_file()
            )


if __name__ == "__main__":
    unittest.main()
