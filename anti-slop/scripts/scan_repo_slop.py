#!/usr/bin/env python3
"""Report deterministic anti-slop findings without editing files."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from lib.anti_slop_engine import (  # noqa: E402
    Finding,
    RegistryError,
    Rule,
    count_decisions,
    fails_at,
    filename_findings,
    load_rules,
    scan_text,
    sort_findings,
)

DEFAULT_EXCLUDES = (".agents/*", ".claude/*", ".codex/*", ".cursor/*")
DEFAULT_MAX_FILE_BYTES = 4 * 1024 * 1024
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "dist", "build", ".next", ".nuxt",
    ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "coverage", ".idea", ".vscode",
}
TEXT_EXTS = {
    ".md", ".mdx", ".txt", ".rst", ".py", ".js", ".jsx", ".ts", ".tsx", ".go",
    ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".hpp",
    ".css", ".scss", ".html", ".json", ".jsonc", ".yaml", ".yml", ".toml",
    ".sh", ".bash", ".zsh", ".ps1",
}
MARKDOWN_EXTS = {".md", ".mdx", ".rst"}


@dataclass
class ScanStats:
    files_considered: int = 0
    files_scanned: int = 0
    files_skipped_too_large: int = 0
    files_unreadable: int = 0


def nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def is_excluded(rel: str, excludes: Sequence[str]) -> bool:
    return any(
        fnmatch.fnmatch(rel, pattern)
        or fnmatch.fnmatch(rel, pattern.rstrip("/*") + "/*")
        for pattern in excludes
    )


def registry_filenames(rules: Sequence[Rule]) -> frozenset[str]:
    return frozenset(
        filename
        for rule in rules
        if rule.kind == "filename" and "repository" in rule.scopes
        for filename in rule.filenames
    )


def is_text_file(path: Path, known_filenames: frozenset[str]) -> bool:
    return path.suffix.lower() in TEXT_EXTS or path.name in known_filenames


def find_git_root(scan_root: Path) -> Path | None:
    current = scan_root
    while True:
        marker = current / ".git"
        try:
            if marker.is_dir() or marker.is_file():
                return current
        except OSError:
            return None
        if current.parent == current:
            return None
        current = current.parent


def path_sort_key(path: Path, root: Path) -> tuple[str, str]:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return rel.casefold(), rel


def git_tracked_files(scan_root: Path, known_filenames: frozenset[str]) -> list[Path] | None:
    """Return tracked and untracked non-ignored files, or None without Git."""
    git_root = find_git_root(scan_root)
    if git_root is None:
        return None
    command = [
        "git", "-c", f"safe.directory={git_root.as_posix()}", "-C", str(scan_root),
        "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", ".",
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None

    paths: dict[str, Path] = {}
    for name in result.stdout.decode("utf-8", errors="replace").split("\0"):
        if not name:
            continue
        path = scan_root / name
        if is_text_file(path, known_filenames) and path.is_file():
            paths[path.as_posix()] = path
    return sorted(paths.values(), key=lambda path: path_sort_key(path, scan_root))


def iter_files(root: Path, known_filenames: frozenset[str]) -> Iterable[Path]:
    git_files = git_tracked_files(root, known_filenames)
    if git_files is not None:
        yield from git_files
        return
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            (name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".DS_Store")),
            key=lambda name: (name.casefold(), name),
        )
        for name in sorted(filenames, key=lambda item: (item.casefold(), item)):
            path = Path(current) / name
            if is_text_file(path, known_filenames):
                yield path


def scan_file(
    path: Path,
    root: Path,
    rules: Sequence[Rule],
    max_file_bytes: int,
) -> tuple[list[Finding], str]:
    rel = path.relative_to(root).as_posix()
    findings = filename_findings(path.name, path=rel, scope="repository", rules=rules)
    try:
        if path.stat().st_size > max_file_bytes:
            return findings, "too_large"
        with path.open("rb") as handle:
            content = handle.read(max_file_bytes + 1)
    except OSError:
        return findings, "unreadable"
    if len(content) > max_file_bytes:
        return findings, "too_large"

    findings.extend(
        scan_text(
            content.decode("utf-8", errors="replace"),
            path=rel,
            scope="repository",
            markdown=path.suffix.lower() in MARKDOWN_EXTS,
            rules=rules,
        )
    )
    return sort_findings(findings), "scanned"


def summary_payload(
    stats: ScanStats,
    findings: Sequence[Finding],
    returned: int,
) -> dict[str, object]:
    return {
        "files_considered": stats.files_considered,
        "files_scanned": stats.files_scanned,
        "files_skipped_too_large": stats.files_skipped_too_large,
        "files_unreadable": stats.files_unreadable,
        "total_findings": len(findings),
        "returned_findings": returned,
        "by_decision": count_decisions(findings),
    }


def format_summary(summary: dict[str, object]) -> str:
    decisions = summary["by_decision"]
    assert isinstance(decisions, dict)
    return (
        "Summary: "
        f"files={summary['files_considered']}, "
        f"scanned={summary['files_scanned']}, "
        f"too_large={summary['files_skipped_too_large']}, "
        f"unreadable={summary['files_unreadable']}; "
        f"findings={summary['total_findings']} "
        f"(BLOCK={decisions['BLOCK']}, TRIM={decisions['TRIM']}, FLAG={decisions['FLAG']}), "
        f"returned={summary['returned_findings']}"
    )


def emit_notices(
    stats: ScanStats,
    *,
    total_findings: int,
    returned_findings: int,
    max_file_bytes: int,
    quiet: bool,
) -> None:
    if quiet:
        return
    omitted = total_findings - returned_findings
    if omitted:
        print(
            f"warning: output truncated; {omitted} of {total_findings} findings omitted",
            file=sys.stderr,
        )
    if stats.files_skipped_too_large:
        print(
            "warning: content skipped for "
            f"{stats.files_skipped_too_large} file(s) larger than {max_file_bytes} bytes",
            file=sys.stderr,
        )
    if stats.files_unreadable:
        print(f"warning: {stats.files_unreadable} file(s) could not be read", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report deterministic anti-slop findings in text files."
    )
    parser.add_argument("path", nargs="?", default=".", help="Repository or file path to scan")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Emit the stable v1 JSON list")
    output.add_argument("--json-v2", action="store_true", help="Emit detailed JSON with scan metadata")
    parser.add_argument(
        "--max-findings", type=nonnegative_int, default=200, help="Maximum findings to print"
    )
    parser.add_argument(
        "--max-file-bytes",
        type=nonnegative_int,
        default=DEFAULT_MAX_FILE_BYTES,
        help="Ignore file content larger than this byte count",
    )
    parser.add_argument(
        "--fail-on-block", action="store_true", help="Exit 2 when BLOCK findings are present"
    )
    parser.add_argument(
        "--fail-on",
        choices=("block", "trim", "flag"),
        help="Exit 2 at this decision threshold or higher",
    )
    parser.add_argument("--summary", action="store_true", help="Print aggregate scan counts")
    parser.add_argument("--quiet", action="store_true", help="Suppress human-readable output and notices")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Skip files whose repo-relative path matches GLOB (repeatable)",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help=f"Also scan default-excluded paths: {', '.join(DEFAULT_EXCLUDES)}",
    )
    args = parser.parse_args(argv)

    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"Path does not exist: {root}", file=sys.stderr)
        return 1

    try:
        rules = load_rules()
    except RegistryError as exc:
        print(f"Invalid anti-slop rule registry: {exc}", file=sys.stderr)
        return 1

    excludes = list(args.exclude)
    if not args.no_default_excludes:
        excludes.extend(DEFAULT_EXCLUDES)

    scan_root = root.parent if root.is_file() else root
    known_filenames = registry_filenames(rules)
    files = [root] if root.is_file() else list(iter_files(scan_root, known_filenames))
    files = sorted(files, key=lambda path: path_sort_key(path, scan_root))

    stats = ScanStats()
    findings: list[Finding] = []
    for path in files:
        rel = path.relative_to(scan_root).as_posix()
        if is_excluded(rel, excludes):
            continue
        stats.files_considered += 1
        file_findings, state = scan_file(path, scan_root, rules, args.max_file_bytes)
        findings.extend(file_findings)
        if state == "scanned":
            stats.files_scanned += 1
        elif state == "too_large":
            stats.files_skipped_too_large += 1
        else:
            stats.files_unreadable += 1

    findings = sort_findings(findings)
    returned = findings[: args.max_findings]
    omitted = len(findings) - len(returned)
    summary = summary_payload(stats, findings, len(returned))

    if args.json:
        print(json.dumps([item.legacy_dict() for item in returned], indent=2, ensure_ascii=False))
    elif args.json_v2:
        print(
            json.dumps(
                {
                    "schema_version": 2,
                    "findings": [item.detailed_dict() for item in returned],
                    "truncated": bool(omitted),
                    "omitted_findings": omitted,
                    "summary": summary,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif not args.quiet:
        if not returned:
            print("No obvious slop patterns found.")
        for item in returned:
            print(
                f"{item.path}:{item.line} - "
                f"{item.code}/{item.severity}: {item.message} :: {item.excerpt}"
            )
        if args.summary:
            print(format_summary(summary))

    if args.summary and args.json and not args.quiet:
        print(format_summary(summary), file=sys.stderr)
    emit_notices(
        stats,
        total_findings=len(findings),
        returned_findings=len(returned),
        max_file_bytes=args.max_file_bytes,
        quiet=args.quiet,
    )

    threshold = args.fail_on or ("block" if args.fail_on_block else None)
    if threshold and fails_at(findings, threshold):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
