#!/usr/bin/env python3
"""Install the canonical anti-slop skill into supported local runtimes."""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


SKILL_NAME = "anti-slop"
NATIVE_TARGETS = {"agents", "claude", "cursor"}
TARGET_CHOICES = ("all", "agents", "claude", "cursor", "codex-legacy")
IGNORED_DIRECTORIES = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
CURSOR_REFERENCE_ROOT = ".agents/skills/anti-slop/references/"
DEFAULT_DESCRIPTION = (
    "Prevent low-quality AI-generated content from entering repository work."
)


class SyncError(RuntimeError):
    """Raised when a destination cannot be updated safely."""


@dataclass(frozen=True)
class TreeManifest:
    directories: Set[Path]
    files: Dict[Path, Path]


@dataclass(frozen=True)
class TreeOperation:
    destination: Path


@dataclass(frozen=True)
class FileOperation:
    destination: Path
    content: bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync anti-slop from its canonical directory to local runtimes."
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--project",
        nargs="?",
        const=".",
        metavar="PATH",
        help="install below PATH (default: current directory)",
    )
    scope.add_argument(
        "--user",
        nargs="?",
        const=str(Path.home()),
        metavar="PATH",
        help="install below PATH (default: home directory)",
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=TARGET_CHOICES,
        help="target to sync; repeat as needed (default: all native targets)",
    )
    parser.add_argument(
        "--legacy-codex",
        action="store_true",
        help="also install into the legacy Codex skills directory",
    )
    parser.add_argument(
        "--cursor-body-only",
        action="store_true",
        help="generate the project Cursor rule without frontmatter",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="show changes without writing them",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="return non-zero when a destination differs from the source",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace destinations that are not recognizable anti-slop skills",
    )
    return parser


def _is_ignored(relative_path: Path) -> bool:
    return (
        any(part in IGNORED_DIRECTORIES for part in relative_path.parts)
        or relative_path.suffix.lower() in IGNORED_SUFFIXES
    )


def _build_manifest(source: Path) -> TreeManifest:
    directories: Set[Path] = set()
    files: Dict[Path, Path] = {}
    for current, directory_names, file_names in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(source)

        kept_directories = []
        for name in directory_names:
            relative = relative_current / name
            path = current_path / name
            if _is_ignored(relative):
                continue
            if path.is_symlink():
                raise SyncError("canonical skill contains a directory symlink: {}".format(relative))
            directories.add(relative)
            kept_directories.append(name)
        directory_names[:] = kept_directories

        for name in file_names:
            relative = relative_current / name
            if _is_ignored(relative):
                continue
            path = current_path / name
            if path.is_symlink():
                raise SyncError("canonical skill contains a file symlink: {}".format(relative))
            files[relative] = path
    return TreeManifest(directories=directories, files=files)


def _split_frontmatter(text: str) -> Tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    return "", text


def _frontmatter_value(frontmatter: str, key: str) -> Optional[str]:
    pattern = re.compile(r"^{}\s*:\s*(.*?)\s*$".format(re.escape(key)))
    for line in frontmatter.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def _cursor_adapter(skill_file: Path, body_only: bool) -> bytes:
    text = skill_file.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    body = body.lstrip("\r\n")
    body = re.sub(
        r"(?<![A-Za-z0-9_./-])references/",
        CURSOR_REFERENCE_ROOT,
        body,
    )
    if not body.endswith("\n"):
        body += "\n"
    if body_only:
        return body.encode("utf-8")

    description = _frontmatter_value(frontmatter, "description") or DEFAULT_DESCRIPTION
    cursor_frontmatter = (
        "---\n"
        "description: {}\n"
        "alwaysApply: false\n"
        "---\n\n"
    ).format(json.dumps(description, ensure_ascii=False))
    return (cursor_frontmatter + body).encode("utf-8")


def _selected_targets(raw_targets: Optional[Sequence[str]], legacy_codex: bool) -> Set[str]:
    selected: Set[str] = set()
    for target in raw_targets or ("all",):
        if target == "all":
            selected.update(NATIVE_TARGETS)
        else:
            selected.add(target)
    if legacy_codex:
        selected.add("codex-legacy")
    return selected


def _codex_user_root(user_root: Path) -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return user_root / ".codex"


def _operations(
    source: Path,
    base: Path,
    project_scope: bool,
    targets: Set[str],
    cursor_body_only: bool,
) -> Tuple[List[TreeOperation], List[FileOperation]]:
    tree_destinations: List[Path] = []
    file_operations: List[FileOperation] = []

    if "agents" in targets or "cursor" in targets:
        tree_destinations.append(base / ".agents" / "skills" / SKILL_NAME)
    if "claude" in targets:
        tree_destinations.append(base / ".claude" / "skills" / SKILL_NAME)
    if "codex-legacy" in targets:
        if project_scope:
            codex_root = base / ".codex"
        else:
            codex_root = _codex_user_root(base)
        tree_destinations.append(codex_root / "skills" / SKILL_NAME)
    if "cursor" in targets and project_scope:
        cursor_rule = base / ".cursor" / "rules" / "antislop.mdc"
        file_operations.append(
            FileOperation(
                destination=cursor_rule,
                content=_cursor_adapter(source / "SKILL.md", cursor_body_only),
            )
        )

    unique_trees: List[TreeOperation] = []
    seen: Set[Path] = set()
    for destination in tree_destinations:
        resolved = destination.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_trees.append(TreeOperation(destination=destination))
    return unique_trees, file_operations


def _actual_entries(destination: Path) -> Tuple[Set[Path], Set[Path]]:
    directories: Set[Path] = set()
    files: Set[Path] = set()
    for current, directory_names, file_names in os.walk(destination, followlinks=False):
        current_path = Path(current)
        relative_current = current_path.relative_to(destination)

        kept_directories = []
        for name in directory_names:
            relative = relative_current / name
            path = current_path / name
            if _is_ignored(relative):
                continue
            if path.is_symlink():
                files.add(relative)
                continue
            directories.add(relative)
            kept_directories.append(name)
        directory_names[:] = kept_directories

        for name in file_names:
            relative = relative_current / name
            if not _is_ignored(relative):
                files.add(relative)
    return directories, files


def _tree_matches(destination: Path, manifest: TreeManifest) -> bool:
    if destination.is_symlink() or not destination.is_dir():
        return False
    try:
        actual_directories, actual_files = _actual_entries(destination)
        if actual_directories != manifest.directories:
            return False
        if actual_files != set(manifest.files):
            return False
        for relative, source_file in manifest.files.items():
            destination_file = destination / relative
            if destination_file.is_symlink():
                return False
            if destination_file.read_bytes() != source_file.read_bytes():
                return False
    except OSError:
        return False
    return True


def _file_matches(destination: Path, content: bytes) -> bool:
    if destination.is_symlink() or not destination.is_file():
        return False
    try:
        return destination.read_bytes() == content
    except OSError:
        return False


def _looks_like_anti_slop(destination: Path) -> bool:
    skill_file = destination / "SKILL.md"
    if not skill_file.is_file() or skill_file.is_symlink():
        return False
    try:
        frontmatter, _ = _split_frontmatter(skill_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return False
    return _frontmatter_value(frontmatter, "name") == SKILL_NAME


def _looks_like_cursor_rule(destination: Path) -> bool:
    if not destination.is_file() or destination.is_symlink():
        return False
    try:
        _, body = _split_frontmatter(destination.read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped == "# Anti-slop"
    return False


def _paths_overlap(source: Path, destination: Path) -> bool:
    source = source.resolve()
    destination = destination.resolve()
    return (
        source == destination
        or source in destination.parents
        or destination in source.parents
    )


def _validate_tree_destination(source: Path, destination: Path, force: bool) -> None:
    if _paths_overlap(source, destination):
        raise SyncError("destination overlaps the canonical skill: {}".format(destination))
    exists = destination.exists() or destination.is_symlink()
    if not exists:
        return
    safe = (
        destination.is_dir()
        and not destination.is_symlink()
        and _looks_like_anti_slop(destination)
    )
    if not safe and not force:
        raise SyncError(
            "refusing to replace an unrecognized destination: {} (use --force)".format(
                destination
            )
        )


def _validate_file_destination(source: Path, destination: Path, force: bool) -> None:
    if _paths_overlap(source, destination):
        raise SyncError("destination overlaps the canonical skill: {}".format(destination))
    exists = destination.exists() or destination.is_symlink()
    if not exists:
        return
    safe = _looks_like_cursor_rule(destination)
    if not safe and not force:
        raise SyncError(
            "refusing to replace an unrecognized Cursor rule: {} (use --force)".format(
                destination
            )
        )


def _remove_path(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _write_tree(source: Path, destination: Path) -> None:
    def ignore(_directory: str, names: Iterable[str]) -> Set[str]:
        return {
            name
            for name in names
            if name in IGNORED_DIRECTORIES or Path(name).suffix.lower() in IGNORED_SUFFIXES
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            dir=str(destination.parent),
            prefix=".{}-stage-".format(destination.name),
        )
    )
    backup = stage.with_name(stage.name + ".backup")
    backup_active = False
    try:
        shutil.copytree(source, stage, ignore=ignore, dirs_exist_ok=True)
        if destination.exists() or destination.is_symlink():
            os.replace(str(destination), str(backup))
            backup_active = True
        try:
            os.replace(str(stage), str(destination))
        except OSError:
            if backup_active:
                try:
                    if destination.exists() or destination.is_symlink():
                        _remove_path(destination)
                    os.replace(str(backup), str(destination))
                    backup_active = False
                except OSError as rollback_error:
                    raise SyncError(
                        "tree update failed and rollback failed; backup retained at {}".format(
                            backup
                        )
                    ) from rollback_error
            raise
        if backup_active:
            _remove_path(backup)
            backup_active = False
    finally:
        if stage.exists() or stage.is_symlink():
            _remove_path(stage)


def _write_file(destination: Path, content: bytes) -> None:
    if destination.is_dir() and not destination.is_symlink():
        shutil.rmtree(destination)
    elif destination.is_symlink():
        destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", delete=False, dir=str(destination.parent), prefix=".antislop-"
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
        os.replace(str(temporary), str(destination))
    finally:
        if temporary.exists():
            temporary.unlink()


def _display(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def sync(args: argparse.Namespace) -> int:
    source = Path(__file__).resolve().parent.parent
    if not (source / "SKILL.md").is_file():
        raise SyncError("canonical SKILL.md not found: {}".format(source))

    project_scope = args.project is not None
    raw_base = args.project if project_scope else args.user
    base = Path(raw_base).expanduser().resolve()
    targets = _selected_targets(args.target, args.legacy_codex)
    manifest = _build_manifest(source)
    tree_operations, file_operations = _operations(
        source=source,
        base=base,
        project_scope=project_scope,
        targets=targets,
        cursor_body_only=args.cursor_body_only,
    )

    tree_drift = [
        operation
        for operation in tree_operations
        if not _tree_matches(operation.destination, manifest)
    ]
    file_drift = [
        operation
        for operation in file_operations
        if not _file_matches(operation.destination, operation.content)
    ]

    if args.check:
        for operation in tree_drift:
            print("drift {}".format(_display(operation.destination, base)))
        for operation in file_drift:
            print("drift {}".format(_display(operation.destination, base)))
        if tree_drift or file_drift:
            return 1
        print("ok")
        return 0

    for operation in tree_drift:
        _validate_tree_destination(source, operation.destination, args.force)
    for operation in file_drift:
        _validate_file_destination(source, operation.destination, args.force)

    if args.dry_run:
        for operation in tree_drift:
            print("would sync {}".format(_display(operation.destination, base)))
        for operation in file_drift:
            print("would sync {}".format(_display(operation.destination, base)))
        if not tree_drift and not file_drift:
            print("ok")
        return 0

    for operation in tree_drift:
        _write_tree(source, operation.destination)
        print("synced {}".format(_display(operation.destination, base)))
    for operation in file_drift:
        _write_file(operation.destination, operation.content)
        print("synced {}".format(_display(operation.destination, base)))
    if not tree_drift and not file_drift:
        print("ok")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return sync(args)
    except (OSError, SyncError, UnicodeError) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
