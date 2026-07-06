#!/usr/bin/env python3
"""Report likely AI slop patterns in a repository.

This scanner is intentionally conservative and dependency-free. It reports
possible issues; it never edits files.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

# Vendored skills are reference material about slop, not repo content.
DEFAULT_EXCLUDES = [".claude/skills/*"]

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

DISPOSABLE_FILENAMES = {
    "SUMMARY.md": ("D7", "BLOCK", "summary file is usually agent residue unless explicitly maintained"),
    "PLAN.md": ("D1", "BLOCK", "plan file is usually temporary unless part of project workflow"),
    "IMPLEMENTATION.md": ("D1", "BLOCK", "implementation narrative is often agent residue"),
    "NOTES.md": ("D1", "TRIM", "notes file needs clear permanent purpose"),
    "CHANGES.md": ("D7", "TRIM", "prefer real CHANGELOG.md or PR text unless this is maintained"),
}

RULES: list[tuple[str, str, str, re.Pattern[str]]] = [
    ("D2", "BLOCK", "fake maturity claim needs evidence", re.compile(r"\b(production[- ]ready|enterprise[- ]grade|battle[- ]tested|secure by default|fully automated)\b", re.I)),
    ("D2", "TRIM", "broad polish word; replace with concrete fact", re.compile(r"\b(robust|seamless|comprehensive|powerful|flexible|scalable|world[- ]class|game[- ]changing)\b", re.I)),
    ("S2", "BLOCK", "verification claim must be backed by actual command output", re.compile(r"\b(tests? pass(?:ed)?|build pass(?:ed|es)?|validated successfully|verified successfully|all checks pass(?:ed)?)\b", re.I)),
    ("S3", "TRIM", "attention-bait phrasing", re.compile(r"\b(shocking|unbelievable|viral|mind[- ]blowing|revolutionary|magic|10x)\b", re.I)),
    ("S1", "TRIM", "template heading", re.compile(r"^\s{0,3}#{1,4}\s+(Overview|Details|Conclusion|Next Steps|Key Features|Benefits)\s*$", re.I)),
    ("S1", "TRIM", "label-colon bullet rhythm", re.compile(r"^\s*[-*]\s+\*\*[^*]{2,40}:\*\*\s+")),
    ("D5", "FLAG", "generated asset or synthetic content needs provenance", re.compile(r"\b(generated image|generated video|generated audio|synthetic media|image prompt|voiceover|transcript:)\b", re.I)),
]


@dataclass
class Finding:
    path: str
    line: int
    code: str
    severity: str
    message: str
    excerpt: str


QUOTE_CHARS = {'"', "'", "`"}


def is_mention(line: str, start: int, end: int) -> bool:
    """True when the matched text is quoted or backticked on its line.

    Docs that list slop phrases, regex source strings, and JSON fixtures all
    wrap the phrase in quotes or backticks — they mention the pattern rather
    than make the claim. Only unquoted occurrences count as findings.
    """
    before = line[:start].rstrip()
    after = line[end:].lstrip()
    for quote in QUOTE_CHARS:
        if before.endswith(quote) and quote in after:
            return True
    # A match inside any string literal on the line (e.g. regex sources,
    # JSON values) sits after an odd number of quote characters.
    for quote in QUOTE_CHARS:
        if line[:start].count(quote) % 2 == 1:
            return True
    return False


def is_excluded(rel: str, excludes: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, pattern.rstrip("/*") + "/*")
        for pattern in excludes
    )


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTS:
        return True
    if path.name in DISPOSABLE_FILENAMES:
        return True
    return False


def git_tracked_files(root: Path) -> list[Path] | None:
    """Return files git considers part of the repo, or None if not applicable.

    Uses `git ls-files` with --exclude-standard so .gitignored paths (build
    output, vendored deps, local scratch/fixtures) are skipped — scanning them
    for slop is noise a real user does not want. Returns None when root is not
    a git worktree or git is unavailable, so the caller falls back to walking.
    """
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    names = out.stdout.decode("utf-8", errors="replace").split("\0")
    return [root / n for n in names if n]


def iter_files(root: Path) -> Iterable[Path]:
    tracked = git_tracked_files(root)
    if tracked is not None:
        for path in tracked:
            if is_text_file(path) and path.is_file():
                yield path
        return
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".DS_Store")]
        for name in filenames:
            path = Path(current) / name
            if is_text_file(path):
                yield path


def scan_file(path: Path, root: Path) -> list[Finding]:
    rel = path.relative_to(root).as_posix()
    findings: list[Finding] = []

    if path.name in DISPOSABLE_FILENAMES:
        code, severity, message = DISPOSABLE_FILENAMES[path.name]
        findings.append(Finding(rel, 1, code, severity, message, path.name))

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return findings
    except Exception:
        return findings

    in_fence = False
    fence_marker = ""
    is_markdown = path.suffix.lower() in {".md", ".mdx", ".rst"}
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if is_markdown:
            fence = re.match(r"^(```+|~~~+)", stripped)
            if fence:
                marker = fence.group(1)[:3]
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = ""
                continue
            if in_fence:
                continue
        if not stripped:
            continue
        for code, severity, message, pattern in RULES:
            match = pattern.search(line)
            if match and not is_mention(line, match.start(), match.end()):
                findings.append(Finding(rel, i, code, severity, message, stripped[:180]))
                break

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report likely AI slop patterns in text files.")
    parser.add_argument("path", nargs="?", default=".", help="Repository or file path to scan")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument("--max-findings", type=int, default=200, help="Maximum findings to print")
    parser.add_argument("--fail-on-block", action="store_true", help="Exit 2 when BLOCK findings are present")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="Skip files whose repo-relative path matches GLOB (repeatable)")
    parser.add_argument("--no-default-excludes", action="store_true",
                        help=f"Also scan default-excluded paths: {DEFAULT_EXCLUDES}")
    args = parser.parse_args(argv)

    excludes = list(args.exclude)
    if not args.no_default_excludes:
        excludes.extend(DEFAULT_EXCLUDES)

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Path does not exist: {root}", file=sys.stderr)
        return 1

    files = [root] if root.is_file() else list(iter_files(root))
    findings: list[Finding] = []
    scan_root = root.parent if root.is_file() else root

    for path in files:
        if is_excluded(path.relative_to(scan_root).as_posix(), excludes):
            continue
        findings.extend(scan_file(path, scan_root))
        if len(findings) >= args.max_findings:
            findings = findings[: args.max_findings]
            break

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2, ensure_ascii=False))
    else:
        if not findings:
            print("No obvious slop patterns found.")
        for f in findings:
            print(f"{f.path}:{f.line} — {f.code}/{f.severity}: {f.message} :: {f.excerpt}")

    if args.fail_on_block and any(f.severity == "BLOCK" for f in findings):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
