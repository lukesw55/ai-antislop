#!/usr/bin/env python3
"""Optional Claude Code Stop hook for anti-slop feedback."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Sequence

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from lib.anti_slop_engine import Finding, Rule, load_rules, scan_text  # noqa: E402

MAX_TRANSCRIPT_TAIL = 2 * 1024 * 1024
MAX_FINDINGS = 5


def transcript_tail(transcript_path: str, limit: int = MAX_TRANSCRIPT_TAIL) -> str:
    """Read at most the final ``limit`` bytes without returning a partial line."""
    try:
        with open(transcript_path, "rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            start = max(0, size - limit)
            previous = b"\n"
            if start:
                handle.seek(start - 1)
                previous = handle.read(1)
            handle.seek(start)
            data = handle.read(limit)
    except OSError:
        return ""

    if start and previous not in {b"\n", b"\r"}:
        newline = data.find(b"\n")
        if newline < 0:
            return ""
        data = data[newline + 1 :]
    return data.decode("utf-8", errors="replace")


def assistant_text(entry: object) -> str:
    if not isinstance(entry, dict) or entry.get("type") != "assistant":
        return ""
    message = entry.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


def last_assistant_text(transcript_path: str) -> str:
    """Extract the last assistant text from the bounded JSONL tail."""
    for line in reversed(transcript_tail(transcript_path).splitlines()):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except (TypeError, ValueError):
            continue
        text = assistant_text(entry)
        if text.strip():
            return text
    return ""


def detect(message: str, rules: Sequence[Rule] | None = None) -> list[Finding]:
    return scan_text(
        message,
        path="assistant-response",
        scope="response",
        markdown=True,
        rules=rules,
    )


def feedback_text(findings: Sequence[Finding]) -> str:
    shown = findings[:MAX_FINDINGS]
    omitted = len(findings) - len(shown)
    lines = [
        "Anti-slop gate found possible AI slop in the final response. Revise before stopping:",
    ]
    for finding in shown:
        lines.append(
            f"- {finding.code}/{finding.severity}: "
            f"{finding.message} ({finding.excerpt!r})"
        )
    if omitted:
        noun = "finding" if omitted == 1 else "findings"
        lines.append(f"- {omitted} additional {noun} omitted.")
    lines.append(
        "Preserve evidence and useful context; remove only unsupported, generic, or distracting material."
    )
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return 0

    message = payload.get("last_assistant_message") or ""
    if not isinstance(message, str) or not message.strip():
        transcript_path = payload.get("transcript_path") or ""
        if not isinstance(transcript_path, str) or not transcript_path:
            return 0
        message = last_assistant_text(transcript_path)
    if not message.strip():
        return 0

    try:
        findings = detect(message, load_rules())
    except Exception:
        # An optional enforcement hook must not block on an invalid registry.
        return 0
    if not findings:
        return 0

    feedback = feedback_text(findings)
    event = payload.get("hook_event_name") or "Stop"
    if os.environ.get("ANTI_SLOP_HOOK_BLOCK") == "1":
        print(json.dumps({"decision": "block", "reason": feedback}))
    else:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": event,
                        "additionalContext": feedback,
                    }
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
