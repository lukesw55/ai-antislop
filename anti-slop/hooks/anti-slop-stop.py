#!/usr/bin/env python3
"""Optional Claude Code Stop hook for anti-slop feedback.

Reads Claude Code hook JSON from stdin. If the final assistant message contains
obvious slop patterns, returns non-error additionalContext so Claude can revise.
Set ANTI_SLOP_HOOK_BLOCK=1 to use a blocking decision instead.
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


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    excerpt: str


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

    message = payload.get("last_assistant_message") or ""
    if not isinstance(message, str) or not message.strip():
        return 0

    findings = detect(message)
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
