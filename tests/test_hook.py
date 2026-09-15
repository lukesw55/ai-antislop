"""Tests for hooks/anti-slop-stop.py — run via: python3 -m unittest discover tests"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "anti-slop" / "hooks" / "anti-slop-stop.py"

ZEBRA_RULE = {
    "id": "T1-zebra",
    "code": "T1",
    "impact": "major",
    "decision": "TRIM",
    "scopes": ["response"],
    "kind": "regex",
    "pattern": "\\bzebra\\b",
    "message": "zebra spotted",
    "fix": "remove the zebra",
}


def make_transcript(directory, messages):
    """Write a minimal Claude Code transcript JSONL with the given assistant texts."""
    path = Path(directory) / "transcript.jsonl"
    lines = [json.dumps({"type": "user", "message": {"content": "do the thing"}})]
    for text in messages:
        lines.append(json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": text}]},
        }))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def run_hook(payload, env_extra=None):
    env = dict(os.environ)
    env.pop("ANTI_SLOP_HOOK_MODE", None)
    env.pop("ANTI_SLOP_HOOK_BLOCK", None)
    env.pop("ANTI_SLOP_RULES", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return proc


def stop_payload(message):
    return {"hook_event_name": "Stop", "last_assistant_message": message}


class HookTests(unittest.TestCase):
    def test_detects_slop_from_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = make_transcript(tmp, [
                "You're absolutely right! All tests passed and the code is production-ready.",
            ])
            proc = run_hook({"hook_event_name": "Stop", "transcript_path": transcript})
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        context = out["systemMessage"]
        self.assertIn("C3", context)
        self.assertIn("S2", context)

    def test_limits_feedback_to_five_findings_and_reports_omitted_count(self):
        message = "\n".join((
            "Great question! I'll now explain.",
            "This production-ready, robust, revolutionary tool uses a generated image. All tests passed.",
            "# Overview",
            "- **Feature:** detail",
            "Let me know if you want me to also add more.",
            "# Summary",
        ))
        proc = run_hook(stop_payload(message))

        self.assertEqual(proc.returncode, 0, proc.stderr)
        context = json.loads(proc.stdout)["systemMessage"]
        finding_lines = re.findall(r"(?m)^- [A-Z][0-9]/", context)
        self.assertEqual(len(finding_lines), 5, context)
        self.assertRegex(context, r"(?m)^- [1-9][0-9]* additional findings? omitted\.$")

    def test_reads_only_bounded_tail_and_finds_last_large_transcript_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "transcript.jsonl"
            early = {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Great question! production-ready."}]},
            }
            padding = {
                "type": "user",
                "message": {"content": "x" * (2 * 1024 * 1024 + 4096)},
            }
            final = {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "All tests passed."}]},
            }
            transcript.write_text(
                "\n".join(json.dumps(entry) for entry in (early, padding, final)) + "\n",
                encoding="utf-8",
            )
            self.assertGreater(transcript.stat().st_size, 2 * 1024 * 1024)
            proc = run_hook({"hook_event_name": "Stop", "transcript_path": str(transcript)})

        self.assertEqual(proc.returncode, 0, proc.stderr)
        context = json.loads(proc.stdout)["systemMessage"]
        self.assertIn("S2", context)
        self.assertNotIn("C3", context)
        self.assertNotIn("D2", context)

    def test_uses_last_assistant_message_not_earlier_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = make_transcript(tmp, [
                "Great question! This is enterprise-grade.",
                "Renamed the variable in auth.ts.",
            ])
            proc = run_hook({"hook_event_name": "Stop", "transcript_path": transcript})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_silent_on_clean_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = make_transcript(tmp, ["Renamed the variable in auth.ts."])
            proc = run_hook({"hook_event_name": "Stop", "transcript_path": transcript})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_ignores_slop_inside_code_fences(self):
        text = "Here is the fixture you asked for:\n```python\nassert 'all tests passed' in log\n```\nDone."
        with tempfile.TemporaryDirectory() as tmp:
            transcript = make_transcript(tmp, [text])
            proc = run_hook({"hook_event_name": "Stop", "transcript_path": transcript})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_noop_when_stop_hook_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = make_transcript(tmp, ["You're absolutely right!"])
            proc = run_hook({
                "hook_event_name": "Stop",
                "transcript_path": transcript,
                "stop_hook_active": True,
            })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_warn_mode_is_default_and_addresses_the_user(self):
        proc = run_hook(stop_payload("Great question! All tests passed."))
        out = json.loads(proc.stdout)
        self.assertEqual(set(out), {"systemMessage"})
        self.assertIn("C3", out["systemMessage"])
        self.assertNotIn("Revise before stopping", out["systemMessage"])
        self.assertNotIn("Preserve evidence", out["systemMessage"])

    def test_context_mode_shape(self):
        proc = run_hook(
            stop_payload("Great question! Happy to help."),
            env_extra={"ANTI_SLOP_HOOK_MODE": "context"},
        )
        out = json.loads(proc.stdout)
        self.assertEqual(set(out), {"hookSpecificOutput"})
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "Stop")
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("C3", context)
        self.assertIn("Revise before stopping", context)

    def test_block_mode_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = make_transcript(tmp, ["Great question! Happy to help."])
            proc = run_hook(
                {"hook_event_name": "Stop", "transcript_path": transcript},
                env_extra={"ANTI_SLOP_HOOK_BLOCK": "1"},
            )
        out = json.loads(proc.stdout)
        self.assertEqual(out["decision"], "block")
        self.assertIn("C3", out["reason"])
        self.assertIn("Revise before stopping", out["reason"])

    def test_mode_env_takes_precedence_over_block_alias(self):
        proc = run_hook(
            stop_payload("Great question!"),
            env_extra={"ANTI_SLOP_HOOK_MODE": "warn", "ANTI_SLOP_HOOK_BLOCK": "1"},
        )
        self.assertEqual(set(json.loads(proc.stdout)), {"systemMessage"})

    def test_invalid_mode_is_ignored(self):
        with_alias = run_hook(
            stop_payload("Great question!"),
            env_extra={"ANTI_SLOP_HOOK_MODE": "loud", "ANTI_SLOP_HOOK_BLOCK": "1"},
        )
        self.assertEqual(json.loads(with_alias.stdout)["decision"], "block")
        without_alias = run_hook(
            stop_payload("Great question!"),
            env_extra={"ANTI_SLOP_HOOK_MODE": "loud"},
        )
        self.assertEqual(set(json.loads(without_alias.stdout)), {"systemMessage"})

    def test_custom_registry_replaces_the_bundled_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp, "rules.json")
            registry.write_text(
                json.dumps({"schema_version": 1, "rules": [ZEBRA_RULE]}), encoding="utf-8"
            )
            env = {"ANTI_SLOP_RULES": str(registry)}
            zebra = run_hook(stop_payload("The zebra crossed the road."), env_extra=env)
            bundled_only = run_hook(stop_payload("Great question!"), env_extra=env)
            default = run_hook(stop_payload("The zebra crossed the road."))
        self.assertIn("T1", json.loads(zebra.stdout)["systemMessage"])
        self.assertEqual(bundled_only.stdout.strip(), "")
        self.assertEqual(default.stdout.strip(), "")

    def test_invalid_custom_registry_fails_open(self):
        proc = run_hook(
            stop_payload("Great question!"),
            env_extra={"ANTI_SLOP_RULES": "/nonexistent/rules.json"},
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_directives_in_the_response_are_ignored(self):
        message = (
            "<!-- anti-slop-ignore-next-line S2-verification-claim -- self-dismissal -->\n"
            "All tests passed.\n"
        )
        proc = run_hook(stop_payload(message))
        self.assertIn("S2", json.loads(proc.stdout)["systemMessage"])

    def test_graceful_on_missing_transcript(self):
        proc = run_hook({"hook_event_name": "Stop", "transcript_path": "/nonexistent/t.jsonl"})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_graceful_on_empty_payload_and_bad_stdin(self):
        for stdin in ("{}", "not json"):
            proc = subprocess.run(
                [sys.executable, str(HOOK)],
                input=stdin, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "")

    def test_payload_message_fast_path(self):
        proc = run_hook(stop_payload("You're absolutely right about that."))
        out = json.loads(proc.stdout)
        self.assertIn("C3", out["systemMessage"])


if __name__ == "__main__":
    unittest.main()
