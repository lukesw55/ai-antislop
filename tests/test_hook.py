"""Tests for hooks/anti-slop-stop.py — run via: python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "anti-slop" / "hooks" / "anti-slop-stop.py"


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


class HookTests(unittest.TestCase):
    def test_detects_slop_from_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            transcript = make_transcript(tmp, [
                "You're absolutely right! All tests passed and the code is production-ready.",
            ])
            proc = run_hook({"hook_event_name": "Stop", "transcript_path": transcript})
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("C3", context)
        self.assertIn("S2", context)

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
        proc = run_hook({
            "hook_event_name": "Stop",
            "last_assistant_message": "You're absolutely right about that.",
        })
        out = json.loads(proc.stdout)
        self.assertIn("C3", out["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
