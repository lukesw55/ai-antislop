#!/usr/bin/env python3
"""Optional Claude Code Stop hook for anti-slop feedback.

Reads Claude Code hook JSON from stdin. The Stop payload does not carry the
assistant's message, so the hook extracts the last assistant text from the
transcript_path JSONL. If that message contains obvious slop patterns, the hook
returns non-error additionalContext so Claude can revise. Set
ANTI_SLOP_HOOK_BLOCK=1 to use a blocking decision instead.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

PATTERNS: list[tuple[str, str, str, re.Pattern[str]]] = [
    ("C3", "TRIM", "sycophantic opener", re.compile(r"^\s*(great question|absolutely|you'?re absolutely right|i'?d be happy to)\b", re.I)),
    ("C2", "TRIM", "tool narration", re.compile(r"\b(i'?ll now|i am now|let me now|first,? i'?ll|next,? i'?ll)\b", re.I)),
    ("C4", "TRIM", "trailing generic summary", re.compile(r"^\s*#{1,3}\s*(summary|recap|conclusion)\s*$", re.I | re.M)),
    ("C5", "TRIM", "unsolicited follow-up bundle", re.compile(r"\blet me know if you (want|would like).*(also|add|further|next)\b", re.I | re.S)),
    ("S1", "TRIM", "template heading", re.compile(r"^\s*#{1,3}\s+(Overview|Details|Conclusion|Next Steps|Key Features|Benefits)\s*$", re.I | re.M)),
    ("S1", "TRIM", "label-colon bullet rhythm", re.compile(r"^\s*[-*]\s+\*\*[^*]{2,40}:\*\*\s+", re.M)),
    ("D2", "BLOCK", "unsupported maturity language", re.compile(r"\b(production[- ]ready|enterprise[- ]grade|battle[- ]tested|fully automated|comprehensive|seamless|robust)\b", re.I)),
    ("S2", "BLOCK", "possible unverified verification claim", re.compile(r"\b(tests? pass(?:ed)?|build pass(?:ed|es)?|validated successfully|verified successfully|all checks pass(?:ed)?)\b", re.I)),
]

FENCE_RE = re.compile(r"^(```+|~~~+).*$\n(?:.*\n)*?^\1\s*$", re.M)


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    excerpt: str


def strip_code_fences(message: str) -> str:
    """Drop fenced code blocks: code the user asked for is not reply slop."""
    return FENCE_RE.sub("", message)


def last_assistant_text(transcript_path: str) -> str:
    """Extract the text of the last assistant message from a transcript JSONL.

    Transcript lines are JSON objects; assistant turns carry
    {"type": "assistant", "message": {"content": [{"type": "text", ...}]}}.
    Returns "" when the file is missing, unreadable, or has no assistant text.
    """
    try:
        with open(transcript_path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return ""

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            continue
        if text.strip():
            return text
    return ""


def detect(message: str) -> list[Finding]:
    findings: list[Finding] = []
    for code, severity, label, pattern in PATTERNS:
        match = pattern.search(message)
        if match:
            excerpt = " ".join(match.group(0).split())[:140]
            findings.append(Finding(code, severity, label, excerpt))
    return findings[:5]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    # Avoid infinite continuation loops.
    if payload.get("stop_hook_active"):
        return 0

    # The Stop payload has no message field today; keep it as a fast path in
    # case a future Claude Code version adds one.
    message = payload.get("last_assistant_message") or ""
    if not isinstance(message, str) or not message.strip():
        transcript_path = payload.get("transcript_path") or ""
        if not isinstance(transcript_path, str) or not transcript_path:
            return 0
        message = last_assistant_text(transcript_path)
    if not message.strip():
        return 0

    findings = detect(strip_code_fences(message))
    if not findings:
        return 0

    event = payload.get("hook_event_name") or "Stop"
    lines = [
        "Anti-slop gate found possible AI slop in the final response. Revise before stopping:",
    ]
    for f in findings:
        lines.append(f"- {f.code}/{f.severity}: {f.message} ({f.excerpt!r})")
    lines.append("Preserve evidence and useful context; remove only unsupported, generic, or distracting material.")

    feedback = "\n".join(lines)

    if os.environ.get("ANTI_SLOP_HOOK_BLOCK") == "1":
        print(json.dumps({"decision": "block", "reason": feedback}))
    else:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": feedback,
            }
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
