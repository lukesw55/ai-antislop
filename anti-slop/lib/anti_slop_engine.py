"""Load and run the deterministic anti-slop rule registry."""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Collection, Iterable, Sequence


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = SKILL_ROOT / "rules" / "rules.json"

VALID_DECISIONS = {"BLOCK", "TRIM", "FLAG"}
VALID_IMPACTS = {"critical", "major", "minor"}
VALID_KINDS = {"filename", "regex", "sequence"}
VALID_SCOPES = {"repository", "response"}
FLAG_VALUES = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
}
SEQUENCE_FLAGS = {"IGNORECASE"}
DECISION_ORDER = {"BLOCK": 0, "TRIM": 1, "FLAG": 2}
COMMON_KEYS = {
    "id",
    "code",
    "impact",
    "decision",
    "scopes",
    "kind",
    "message",
    "fix",
    "notes",
}
EXCLUSION_KEYS = {"unless_preceded_by", "unless_followed_by"}
KIND_KEYS = {
    "filename": {"filenames"},
    "regex": {"pattern", "flags"} | EXCLUSION_KEYS,
    "sequence": {"line_pattern", "flags", "min_consecutive"} | EXCLUSION_KEYS,
}

# Whitespace and Markdown emphasis markers allowed between an exclusion word
# and the matched text on the same line.
_EXCLUSION_GAP = r"[\s*_`~]*"
_PRECEDED_TEMPLATE = r"(?<![\w'])(?:%s)" + _EXCLUSION_GAP + r"\Z"

# A code fence still opens and closes inside the containers a Markdown file
# commonly wraps it in: blockquotes, bullet items and ordered items. This is a
# bounded prefix, not a CommonMark parser.
_CONTAINER_PREFIX = (
    r"(?:[ \t]{0,3}(?:>[ \t]{0,3})+|[ \t]{0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+)*"
)
_FENCE_LINE = re.compile(r"^" + _CONTAINER_PREFIX + r"[ \t]{0,3}(`{3,}|~{3,})(.*)$")
_FOLLOWED_TEMPLATE = r"\A" + _EXCLUSION_GAP + r"(?:%s)(?![\w'])"

# Inline suppression directives. The whole line must be the comment.
FILE_DIRECTIVE_MAX_LINE = 10
_DIRECTIVE_HEAD = re.compile(
    r"^﻿?[ \t]*(?P<opener><!--|#|//)[ \t]*"
    r"anti-slop-ignore-(?P<scope>next-line|file)(?![\w-])(?P<rest>.*)$"
)
_DIRECTIVE_BODY = re.compile(r"^[ \t]+(?P<rule>\S+)[ \t]+--[ \t]+(?P<reason>\S.*?)[ \t]*$")


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
    min_consecutive: int = 0
    # Each entry pairs an optional selector, matched against the whole matched
    # text, with the compiled exclusion. A None selector applies to every
    # alternative of the rule's pattern.
    preceded_exclusions: tuple[tuple[re.Pattern[str] | None, re.Pattern[str]], ...] = ()
    followed_exclusions: tuple[tuple[re.Pattern[str] | None, re.Pattern[str]], ...] = ()


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


@dataclass(frozen=True)
class Suppression:
    """A valid inline directive. ``target_line`` is None for file-wide scope."""

    rule_id: str
    scope: str
    directive_line: int
    target_line: int | None
    reason: str


@dataclass(frozen=True)
class DirectiveProblem:
    line: int
    reason: str


def _require_text(raw: dict[str, object], key: str, rule_id: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{rule_id}: {key} must be a non-empty string")
    return value


def _compile_flags(raw: dict[str, object], rule_id: str, allowed: set[str]) -> int:
    raw_flags = raw.get("flags", [])
    if not isinstance(raw_flags, list) or not all(isinstance(flag, str) for flag in raw_flags):
        raise RegistryError(f"{rule_id}: flags must be a list of strings")
    unknown_flags = set(raw_flags) - FLAG_VALUES.keys()
    if unknown_flags:
        raise RegistryError(f"{rule_id}: unknown flags {sorted(unknown_flags)}")
    disallowed = set(raw_flags) - allowed
    if disallowed:
        raise RegistryError(
            f"{rule_id}: flags {sorted(disallowed)} are not allowed for {raw.get('kind')} rules"
        )
    flags = 0
    for flag in raw_flags:
        flags |= FLAG_VALUES[flag]
    return flags


def _compile_pattern(source: str, flags: int, rule_id: str, key: str) -> re.Pattern[str]:
    try:
        return re.compile(source, flags)
    except re.error as exc:
        raise RegistryError(f"{rule_id}: invalid {key} regex: {exc}") from exc


def _compile_exclusion_list(
    items: object, key: str, rule_id: str, template: str
) -> re.Pattern[str]:
    if (
        not isinstance(items, list)
        or not items
        or not all(isinstance(item, str) and item.strip() for item in items)
    ):
        raise RegistryError(
            f"{rule_id}: {key} must be a non-empty list of strings, "
            "or an object mapping matched text to such lists"
        )
    alternatives = "|".join(f"(?:{item})" for item in items)
    return _compile_pattern(template % alternatives, re.IGNORECASE, rule_id, key)


def _compile_exclusion(
    raw: dict[str, object], key: str, rule_id: str, template: str
) -> tuple[tuple[re.Pattern[str] | None, re.Pattern[str]], ...]:
    """Compile an ``unless_*`` field.

    A list applies to every alternative of the rule's pattern. An object maps
    a regex, which must match the whole matched text, to the list that applies
    to that alternative only.
    """
    if key not in raw:
        return ()
    items = raw[key]
    if isinstance(items, list):
        return ((None, _compile_exclusion_list(items, key, rule_id, template)),)
    if isinstance(items, dict) and items:
        compiled: list[tuple[re.Pattern[str] | None, re.Pattern[str]]] = []
        for selector_source, selected_items in items.items():
            if not isinstance(selector_source, str) or not selector_source.strip():
                raise RegistryError(f"{rule_id}: {key} keys must be non-empty regex strings")
            selector = _compile_pattern(selector_source, re.IGNORECASE, rule_id, key)
            compiled.append(
                (selector, _compile_exclusion_list(selected_items, key, rule_id, template))
            )
        return tuple(compiled)
    raise RegistryError(
        f"{rule_id}: {key} must be a non-empty list of strings, "
        "or an object mapping matched text to such lists"
    )


def _compile_rule(raw: object, index: int) -> Rule:
    if not isinstance(raw, dict):
        raise RegistryError(f"rules[{index}] must be an object")

    rule_id = _require_text(raw, "id", f"rules[{index}]")
    kind = _require_text(raw, "kind", rule_id)
    if kind not in VALID_KINDS:
        raise RegistryError(f"{rule_id}: invalid detector kind {kind!r}")

    # Keys are checked against the detector kind, so a field that is valid for
    # another kind cannot sit unused in a rule that ignores it.
    unknown_keys = set(raw) - COMMON_KEYS - KIND_KEYS[kind]
    if unknown_keys:
        raise RegistryError(
            f"{rule_id}: keys {sorted(unknown_keys)} are not allowed for a {kind} rule"
        )

    code = _require_text(raw, "code", rule_id)
    impact = _require_text(raw, "impact", rule_id)
    decision = _require_text(raw, "decision", rule_id)
    message = _require_text(raw, "message", rule_id)
    fix = _require_text(raw, "fix", rule_id)

    if not re.fullmatch(r"[A-Z][0-9]+", code):
        raise RegistryError(f"{rule_id}: invalid code {code!r}")
    if impact not in VALID_IMPACTS:
        raise RegistryError(f"{rule_id}: invalid impact {impact!r}")
    if decision not in VALID_DECISIONS:
        raise RegistryError(f"{rule_id}: invalid decision {decision!r}")

    raw_scopes = raw.get("scopes")
    if not isinstance(raw_scopes, list) or not raw_scopes:
        raise RegistryError(f"{rule_id}: scopes must be a non-empty list")
    # Validate every item before hashing: an unhashable entry such as a nested
    # list would otherwise raise TypeError instead of RegistryError.
    for scope in raw_scopes:
        if not isinstance(scope, str):
            raise RegistryError(f"{rule_id}: scopes must contain only strings")
        if scope not in VALID_SCOPES:
            raise RegistryError(
                f"{rule_id}: unknown scope {scope!r}; expected one of {sorted(VALID_SCOPES)}"
            )
    scopes = frozenset(raw_scopes)

    pattern = None
    filenames: tuple[str, ...] = ()
    min_consecutive = 0
    if kind == "regex":
        source = _require_text(raw, "pattern", rule_id)
        flags = _compile_flags(raw, rule_id, set(FLAG_VALUES))
        pattern = _compile_pattern(source, flags, rule_id, "pattern")
    elif kind == "sequence":
        source = _require_text(raw, "line_pattern", rule_id)
        flags = _compile_flags(raw, rule_id, SEQUENCE_FLAGS)
        pattern = _compile_pattern(source, flags, rule_id, "line_pattern")
        raw_min = raw.get("min_consecutive")
        if isinstance(raw_min, bool) or not isinstance(raw_min, int) or raw_min < 2:
            raise RegistryError(f"{rule_id}: min_consecutive must be an integer >= 2")
        min_consecutive = raw_min
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
        min_consecutive=min_consecutive,
        preceded_exclusions=_compile_exclusion(
            raw, "unless_preceded_by", rule_id, _PRECEDED_TEMPLATE
        ),
        followed_exclusions=_compile_exclusion(
            raw, "unless_followed_by", rule_id, _FOLLOWED_TEMPLATE
        ),
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
        match = _FENCE_LINE.match(candidate)
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


def excluded_by_context(rule: Rule, line: str, start: int, end: int) -> bool:
    """Return True when a same-line exclusion declared by the rule applies to this match."""
    matched = line[start:end]
    for selector, exclusion in rule.preceded_exclusions:
        if selector is not None and selector.fullmatch(matched) is None:
            continue
        if exclusion.search(line[:start]):
            return True
    for selector, exclusion in rule.followed_exclusions:
        if selector is not None and selector.fullmatch(matched) is None:
            continue
        if exclusion.match(line[end:]):
            return True
    return False


def _line_starts(text: str) -> list[int]:
    return [0] + [match.end() for match in re.finditer("\n", text)]


def _line_details(text: str, starts: Sequence[int], offset: int) -> tuple[int, int, str]:
    line_index = max(0, bisect.bisect_right(starts, offset) - 1)
    line_start = starts[line_index]
    line_end = text.find("\n", line_start)
    if line_end == -1:
        line_end = len(text)
    return line_index + 1, line_start, text[line_start:line_end].rstrip("\r")


def _excerpt(line: str) -> str:
    return " ".join(line.strip().split())[:180]


def _regex_findings(
    rule: Rule,
    text: str,
    searchable: str,
    starts: Sequence[int],
    path: str,
    seen: set[tuple[str, int]],
    skipped: frozenset[int],
) -> list[Finding]:
    assert rule.pattern is not None
    findings: list[Finding] = []
    for match in rule.pattern.finditer(searchable):
        matched = match.group(0)
        if not matched.strip():
            continue
        # Anchor on the first non-blank character so a pattern that swallows
        # leading blank lines is still attributed to the line with content.
        anchor = match.start() + (len(matched) - len(matched.lstrip()))
        line_number, line_start, line = _line_details(text, starts, anchor)
        local_start = anchor - line_start
        local_end = min(len(line), max(local_start, match.end() - line_start))
        if is_mention(line, local_start, local_end):
            continue
        if excluded_by_context(rule, line, local_start, local_end):
            continue
        if line_number in skipped:
            continue
        key = (rule.rule_id, line_number)
        if key in seen:
            continue
        seen.add(key)
        findings.append(_finding(rule, path, line_number, _excerpt(line)))
    return findings


def _sequence_findings(
    rule: Rule,
    text: str,
    searchable: str,
    starts: Sequence[int],
    path: str,
    seen: set[tuple[str, int]],
    skipped: frozenset[int],
) -> list[Finding]:
    """Report one finding per run of at least ``min_consecutive`` matching lines."""
    assert rule.pattern is not None
    findings: list[Finding] = []
    original_lines = text.split("\n")
    run_start: int | None = None
    run_length = 0

    def flush() -> None:
        nonlocal run_start, run_length
        if run_start is not None and run_length >= rule.min_consecutive:
            line_number = run_start + 1
            key = (rule.rule_id, line_number)
            if line_number not in skipped and key not in seen:
                seen.add(key)
                line = original_lines[run_start].rstrip("\r")
                findings.append(_finding(rule, path, line_number, _excerpt(line)))
        run_start = None
        run_length = 0

    for index, masked in enumerate(searchable.split("\n")):
        line = masked.rstrip("\r")
        match = rule.pattern.search(line)
        original = original_lines[index].rstrip("\r")
        if (
            match is not None
            and match.group(0).strip()
            and not is_mention(original, match.start(), match.end())
            and not excluded_by_context(rule, original, match.start(), match.end())
        ):
            if run_start is None:
                run_start = index
            run_length += 1
        else:
            flush()
    flush()
    return findings


def scan_text(
    text: str,
    *,
    path: str,
    scope: str,
    markdown: bool,
    rules: Sequence[Rule] | None = None,
    skip_lines: Collection[int] = (),
) -> list[Finding]:
    """Run text rules for ``scope``. Lines in ``skip_lines`` never produce findings."""
    if scope not in VALID_SCOPES:
        raise ValueError(f"invalid scan scope: {scope}")

    active_rules = rules or load_rules()
    searchable = mask_markdown_fences(text) if markdown else text
    starts = _line_starts(text)
    skipped = frozenset(skip_lines)
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()

    for rule in active_rules:
        if scope not in rule.scopes or rule.pattern is None:
            continue
        if rule.kind == "regex":
            findings.extend(
                _regex_findings(rule, text, searchable, starts, path, seen, skipped)
            )
        elif rule.kind == "sequence":
            findings.extend(
                _sequence_findings(rule, text, searchable, starts, path, seen, skipped)
            )

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


def parse_directives(
    text: str,
    rules: Sequence[Rule],
    *,
    markdown: bool,
) -> tuple[list[Suppression], list[DirectiveProblem]]:
    """Parse whole-line ``anti-slop-ignore-*`` comments.

    Accepted forms, each on a line of its own (leading whitespace allowed),
    written as an HTML comment, a ``#`` comment, or a ``//`` comment:

        `<!-- anti-slop-ignore-next-line RULE_ID -- reason -->`
        `# anti-slop-ignore-file RULE_ID -- reason`
        `// anti-slop-ignore-next-line RULE_ID -- reason`

    Directives inside Markdown fences are not recognized when ``markdown`` is
    true. Invalid directives are reported as problems and suppress nothing.
    """
    known = {rule.rule_id for rule in rules}
    searchable = mask_markdown_fences(text) if markdown else text
    line_count = len(text.splitlines())
    suppressions: list[Suppression] = []
    problems: list[DirectiveProblem] = []

    for index, raw in enumerate(searchable.split("\n")):
        line_number = index + 1
        head = _DIRECTIVE_HEAD.match(raw.rstrip("\r"))
        if head is None:
            continue
        rest = head.group("rest")
        if head.group("opener") == "<!--":
            closer = rest.find("-->")
            if closer < 0 or rest[closer + 3 :].strip():
                problems.append(
                    DirectiveProblem(
                        line_number,
                        "HTML comment directive must be the whole line and close with --> at its end",
                    )
                )
                continue
            rest = rest[:closer]
        body = _DIRECTIVE_BODY.match(rest)
        if body is None:
            problems.append(
                DirectiveProblem(
                    line_number, "expected 'anti-slop-ignore-<scope> <RULE_ID> -- <reason>'"
                )
            )
            continue
        rule_id = body.group("rule")
        if rule_id not in known:
            problems.append(DirectiveProblem(line_number, f"unknown rule id {rule_id!r}"))
            continue
        reason = body.group("reason")
        if head.group("scope") == "file":
            if line_number > FILE_DIRECTIVE_MAX_LINE:
                problems.append(
                    DirectiveProblem(
                        line_number,
                        "anti-slop-ignore-file must appear within the first "
                        f"{FILE_DIRECTIVE_MAX_LINE} lines",
                    )
                )
                continue
            suppressions.append(Suppression(rule_id, "file", line_number, None, reason))
        else:
            target = line_number + 1
            if target > line_count:
                problems.append(
                    DirectiveProblem(line_number, "anti-slop-ignore-next-line has no following line")
                )
                continue
            suppressions.append(Suppression(rule_id, "next-line", line_number, target, reason))

    return suppressions, problems


def apply_suppressions(
    findings: Iterable[Finding],
    suppressions: Sequence[Suppression],
) -> tuple[list[Finding], list[Finding]]:
    """Split findings into (active, suppressed) using exact rule ids only."""
    file_rules = {item.rule_id for item in suppressions if item.scope == "file"}
    targets = {
        (item.rule_id, item.target_line) for item in suppressions if item.scope == "next-line"
    }
    active: list[Finding] = []
    suppressed: list[Finding] = []
    for finding in findings:
        if finding.rule_id in file_rules or (finding.rule_id, finding.line) in targets:
            suppressed.append(finding)
        else:
            active.append(finding)
    return sort_findings(active), sort_findings(suppressed)


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
