"""Load and run the deterministic anti-slop rule registry."""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = SKILL_ROOT / "rules" / "rules.json"

VALID_DECISIONS = {"BLOCK", "TRIM", "FLAG"}
VALID_IMPACTS = {"critical", "major", "minor"}
VALID_KINDS = {"filename", "regex"}
VALID_SCOPES = {"repository", "response"}
FLAG_VALUES = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
}
DECISION_ORDER = {"BLOCK": 0, "TRIM": 1, "FLAG": 2}


class RegistryError(ValueError):
    """Raised when the executable rule registry is invalid."""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    code: str
    impact: str
    decision: str
    scopes: frozenset[str]
    kind: str
    message: str
    fix: str
    pattern: re.Pattern[str] | None = None
    filenames: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    code: str
    severity: str
    message: str
    excerpt: str
    rule_id: str
    impact: str
    fix: str

    def legacy_dict(self) -> dict[str, object]:
        """Return the stable v1 JSON shape used by ``--json``."""
        return {
            "path": self.path,
            "line": self.line,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "excerpt": self.excerpt,
        }

    def detailed_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "rule_id": self.rule_id,
            "code": self.code,
            "impact": self.impact,
            "decision": self.severity,
            "message": self.message,
            "fix": self.fix,
            "excerpt": self.excerpt,
        }


def _require_text(raw: dict[str, object], key: str, rule_id: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{rule_id}: {key} must be a non-empty string")
    return value


def _compile_rule(raw: object, index: int) -> Rule:
    if not isinstance(raw, dict):
        raise RegistryError(f"rules[{index}] must be an object")

    rule_id = _require_text(raw, "id", f"rules[{index}]")
    code = _require_text(raw, "code", rule_id)
    impact = _require_text(raw, "impact", rule_id)
    decision = _require_text(raw, "decision", rule_id)
    kind = _require_text(raw, "kind", rule_id)
    message = _require_text(raw, "message", rule_id)
    fix = _require_text(raw, "fix", rule_id)

    if not re.fullmatch(r"[A-Z][0-9]+", code):
        raise RegistryError(f"{rule_id}: invalid code {code!r}")
    if impact not in VALID_IMPACTS:
        raise RegistryError(f"{rule_id}: invalid impact {impact!r}")
    if decision not in VALID_DECISIONS:
        raise RegistryError(f"{rule_id}: invalid decision {decision!r}")
    if kind not in VALID_KINDS:
        raise RegistryError(f"{rule_id}: invalid detector kind {kind!r}")

    raw_scopes = raw.get("scopes")
    if not isinstance(raw_scopes, list) or not raw_scopes:
        raise RegistryError(f"{rule_id}: scopes must be a non-empty list")
    scopes = frozenset(raw_scopes)
    if not all(isinstance(scope, str) for scope in scopes) or not scopes <= VALID_SCOPES:
        raise RegistryError(f"{rule_id}: invalid scopes")

    pattern = None
    filenames: tuple[str, ...] = ()
    if kind == "regex":
        source = _require_text(raw, "pattern", rule_id)
        raw_flags = raw.get("flags", [])
        if not isinstance(raw_flags, list) or not all(isinstance(flag, str) for flag in raw_flags):
            raise RegistryError(f"{rule_id}: flags must be a list of strings")
        unknown_flags = set(raw_flags) - FLAG_VALUES.keys()
        if unknown_flags:
            raise RegistryError(f"{rule_id}: unknown flags {sorted(unknown_flags)}")
        flags = 0
        for flag in raw_flags:
            flags |= FLAG_VALUES[flag]
        try:
            pattern = re.compile(source, flags)
        except re.error as exc:
            raise RegistryError(f"{rule_id}: invalid regex: {exc}") from exc
    else:
        raw_filenames = raw.get("filenames")
        if not isinstance(raw_filenames, list) or not raw_filenames:
            raise RegistryError(f"{rule_id}: filenames must be a non-empty list")
        if not all(isinstance(name, str) and name for name in raw_filenames):
            raise RegistryError(f"{rule_id}: filenames must contain non-empty strings")
        filenames = tuple(raw_filenames)

    return Rule(
        rule_id=rule_id,
        code=code,
        impact=impact,
        decision=decision,
        scopes=scopes,
        kind=kind,
        message=message,
        fix=fix,
        pattern=pattern,
        filenames=filenames,
    )


@lru_cache(maxsize=8)
def _load_rules_cached(path_string: str) -> tuple[Rule, ...]:
    path = Path(path_string)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot load rule registry {path}: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RegistryError("rule registry schema_version must be 1")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise RegistryError("rule registry must contain a non-empty rules list")

    rules = tuple(_compile_rule(raw, index) for index, raw in enumerate(raw_rules))
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise RegistryError("rule ids must be unique")
    return rules


def load_rules(path: Path | None = None) -> tuple[Rule, ...]:
    registry = (path or DEFAULT_REGISTRY).resolve()
    return _load_rules_cached(str(registry))


def mask_markdown_fences(text: str) -> str:
    """Replace fenced blocks with spaces while preserving offsets and lines."""
    output: list[str] = []
    fence_char = ""
    fence_length = 0

    for line in text.splitlines(keepends=True):
        candidate = line.rstrip("\r\n")
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", candidate)
        if fence_char:
            output.append(_blank_line(line))
            if match:
                marker = match.group(1)
                trailer = match.group(2).strip()
                if marker[0] == fence_char and len(marker) >= fence_length and not trailer:
                    fence_char = ""
                    fence_length = 0
            continue
        if match:
            marker = match.group(1)
            fence_char = marker[0]
            fence_length = len(marker)
            output.append(_blank_line(line))
            continue
        output.append(line)

    return "".join(output)


def _blank_line(line: str) -> str:
    return "".join(char if char in "\r\n" else " " for char in line)


def _is_apostrophe(line: str, index: int) -> bool:
    return (
        line[index] == "'"
        and index > 0
        and index + 1 < len(line)
        and line[index - 1].isalnum()
        and line[index + 1].isalnum()
    )


def quoted_spans(line: str) -> list[tuple[int, int]]:
    """Return simple quoted or backticked spans, excluding apostrophes."""
    spans: list[tuple[int, int]] = []
    quote = ""
    start = 0
    escaped = False

    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote and not _is_apostrophe(line, index):
                spans.append((start, index + 1))
                quote = ""
            continue
        if char in {'"', "'", "`"} and not _is_apostrophe(line, index):
            quote = char
            start = index

    if quote:
        spans.append((start, len(line)))
    return spans


def is_mention(line: str, start: int, end: int) -> bool:
    return any(start >= span_start and end <= span_end for span_start, span_end in quoted_spans(line))


def _line_starts(text: str) -> list[int]:
    return [0] + [match.end() for match in re.finditer("\n", text)]


def _line_details(text: str, starts: Sequence[int], offset: int) -> tuple[int, int, str]:
    line_index = max(0, bisect.bisect_right(starts, offset) - 1)
    line_start = starts[line_index]
    line_end = text.find("\n", line_start)
    if line_end == -1:
        line_end = len(text)
    return line_index + 1, line_start, text[line_start:line_end].rstrip("\r")


def scan_text(
    text: str,
    *,
    path: str,
    scope: str,
    markdown: bool,
    rules: Sequence[Rule] | None = None,
) -> list[Finding]:
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid scan scope: {scope}")

    active_rules = rules or load_rules()
    searchable = mask_markdown_fences(text) if markdown else text
    starts = _line_starts(text)
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()

    for rule in active_rules:
        if rule.kind != "regex" or scope not in rule.scopes or rule.pattern is None:
            continue
        for match in rule.pattern.finditer(searchable):
            if not match.group(0).strip():
                continue
            line_number, line_start, line = _line_details(text, starts, match.start())
            local_start = match.start() - line_start
            local_end = min(len(line), max(local_start, match.end() - line_start))
            if is_mention(line, local_start, local_end):
                continue
            key = (rule.rule_id, line_number)
            if key in seen:
                continue
            seen.add(key)
            excerpt = " ".join(line.strip().split())[:180]
            findings.append(_finding(rule, path, line_number, excerpt))

    return sort_findings(findings)


def filename_findings(
    filename: str,
    *,
    path: str,
    scope: str = "repository",
    rules: Sequence[Rule] | None = None,
) -> list[Finding]:
    active_rules = rules or load_rules()
    return sort_findings(
        _finding(rule, path, 1, filename)
        for rule in active_rules
        if rule.kind == "filename" and scope in rule.scopes and filename in rule.filenames
    )


def _finding(rule: Rule, path: str, line: int, excerpt: str) -> Finding:
    return Finding(
        path=path,
        line=line,
        code=rule.code,
        severity=rule.decision,
        message=rule.message,
        excerpt=excerpt,
        rule_id=rule.rule_id,
        impact=rule.impact,
        fix=rule.fix,
    )


def sort_findings(findings: Iterable[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda finding: (
            DECISION_ORDER[finding.severity],
            finding.path.casefold(),
            finding.line,
            finding.rule_id,
        ),
    )


def count_decisions(findings: Iterable[Finding]) -> dict[str, int]:
    counts = {decision: 0 for decision in ("BLOCK", "TRIM", "FLAG")}
    for finding in findings:
        counts[finding.severity] += 1
    return counts


def fails_at(findings: Iterable[Finding], threshold: str) -> bool:
    normalized = threshold.upper()
    if normalized not in DECISION_ORDER:
        raise ValueError(f"invalid threshold: {threshold}")
    limit = DECISION_ORDER[normalized]
    return any(DECISION_ORDER[finding.severity] <= limit for finding in findings)
