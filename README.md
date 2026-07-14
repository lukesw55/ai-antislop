# anti-slop

`anti-slop` is an Agent Skill for reviewing repository-facing output. It combines an instruction workflow for semantic review with an optional Python engine for deterministic findings. The skill is distributed from one canonical directory to Claude Code, Codex, and Cursor.

The core rule is simple: remove unsupported or generic material without deleting behavior, evidence, constraints, boundary checks, citations, or operational detail.

## Execution model

Use this sequence for new output, existing files, and diffs:

`Context -> Detect -> Classify -> Gate -> Rewrite -> Verify -> Deliver`

1. Establish the artifact, audience, repository conventions, evidence, and allowed scope.
2. Run deterministic detectors separately from semantic review.
3. Assign a slop class, impact, and decision to each finding.
4. Return `PASS` or `FAIL` for evidence, behavior, contamination, and delivery gates.
5. Rewrite only when the mode or user authorizes edits.
6. Compare the result with the source and rerun relevant checks when available.
7. Deliver the cleaned artifact or a read-only audit with unresolved evidence stated.

The workflow adopts instructional ideas from [Hallmark](https://github.com/Nutlope/hallmark), including progressive reference loading, layered classification, and explicit gates. Hallmark is an instruction architecture. The registry, Python engine, scanner, hook, synchronization script, and tests in this repository are this project's implementation.

The skill has three modes:

| Mode | Purpose | Mutation policy |
|---|---|---|
| Gate | Check new output before delivery | Rewrite the draft within the requested scope |
| Sweep | Audit existing material | Read-only unless edits are requested separately |
| Diff | Review a patch or pull request | Read-only unless fixes are requested separately |

Impact and decision are separate:

| Layer | Values | Meaning |
|---|---|---|
| Impact | `critical`, `major`, `minor` | Cost if the issue ships |
| Decision | `BLOCK`, `TRIM`, `FLAG`, `IGNORE` | Action for the current task |

## Rules

The reference catalog contains 44 semantic patterns. Agents use these patterns with repository context; they are not all regular expressions.

| Surface | IDs | Count |
|---|---|---:|
| Code | A1-A10 | 10 |
| Documentation | B1-B10 | 10 |
| Assistant responses | C1-C9 | 9 |
| Repository contamination | D1-D8 | 8 |
| Multimodal material | M1-M7 | 7 |

The executable registry contains 16 deterministic detectors: 5 filename rules and 11 regex rules. [`anti-slop/rules/rules.json`](anti-slop/rules/rules.json) is the source of truth for those detectors. [`anti-slop/lib/anti_slop_engine.py`](anti-slop/lib/anti_slop_engine.py) loads the registry and is shared by the scanner and hook.

A deterministic match is a candidate finding. Semantic claims, behavior preservation, and false positives still require context. Detailed guidance lives in [`anti-slop/references/`](anti-slop/references/) and is loaded only when needed.

## Install and synchronize

Clone the repository:

```bash
git clone https://github.com/lukesw55/ai-antislop.git
cd ai-antislop
```

The canonical source is [`anti-slop/`](anti-slop/). Do not maintain runtime copies by hand.

Install all native project targets:

```bash
python3 anti-slop/scripts/sync_skill.py --project .
```

Install user-scoped targets:

```bash
python3 anti-slop/scripts/sync_skill.py --user "$HOME"
```

Use `python` instead of `python3` where that is the configured Python command.

Default project synchronization creates:

| Runtime | Destination |
|---|---|
| Codex and Cursor Agent Skills | `.agents/skills/anti-slop/` |
| Claude Code | `.claude/skills/anti-slop/` |
| Cursor project rule | `.cursor/rules/antislop.mdc` |

Default user synchronization creates `~/.agents/skills/anti-slop/` and `~/.claude/skills/anti-slop/`. Cursor can use the user-scoped `.agents` copy; the script does not create a user-level `.cursor` rule.

Legacy Codex installation is opt-in. Project scope writes `.codex/skills/anti-slop/`. User scope uses `$CODEX_HOME/skills/anti-slop/` when `CODEX_HOME` is set, otherwise `~/.codex/skills/anti-slop/`.

Synchronization options:

| Option | Behavior |
|---|---|
| `--target all|agents|claude|cursor|codex-legacy` | Select a target; repeat the option to select several |
| `--check` | Report drift without writing; return 1 when a target differs |
| `--dry-run` | Report planned writes without changing targets |
| `--force` | Replace a destination that is not recognized as this skill or Cursor rule |
| `--cursor-body-only` | Generate a project Cursor rule without MDC frontmatter for manual mapping |
| `--legacy-codex` | Add the legacy Codex target to the selected targets |

The sync command returns 0 on success, 1 for drift in `--check`, and 2 for an error or refused replacement.

The default Cursor rule has minimal MDC frontmatter. Existing Cursor rules are replaced without `--force` only when their body starts with `# Anti-slop`. Skill trees are replaced without `--force` only when `SKILL.md` identifies `name: anti-slop`. Tree updates use a staged sibling and restore the previous tree if the commit step fails.

Examples:

```bash
# Install only Claude Code and Codex/Cursor Agent Skill targets.
python3 anti-slop/scripts/sync_skill.py --project . --target claude --target agents

# Check every native project target for drift.
python3 anti-slop/scripts/sync_skill.py --project . --check

# Preview a user install that also includes legacy Codex.
python3 anti-slop/scripts/sync_skill.py --user "$HOME" --legacy-codex --dry-run
```

## Invoke the skill

Invoke by name when the review matters. Runtime discovery can vary by version and configuration; this repository does not promise deterministic automatic activation.

| Runtime | Example request |
|---|---|
| Claude Code | `Use the anti-slop skill in Sweep mode on README.md.` |
| Codex | `$anti-slop Review the current diff in Diff mode.` |
| Cursor | `Apply anti-slop in Gate mode to this change.` |

The same `SKILL.md`, references, and executable registry are copied to Claude and Agent Skill targets. The Cursor adapter rewrites reference paths to the `.agents` installation.

## Static scanner

[`anti-slop/scripts/scan_repo_slop.py`](anti-slop/scripts/scan_repo_slop.py) is dependency-free and read-only. Its current help is:

```text
usage: scan_repo_slop.py [-h] [--json | --json-v2]
                         [--max-findings MAX_FINDINGS]
                         [--max-file-bytes MAX_FILE_BYTES] [--fail-on-block]
                         [--fail-on {block,trim,flag}] [--summary] [--quiet]
                         [--exclude GLOB] [--no-default-excludes]
                         [path]

Report deterministic anti-slop findings in text files.

positional arguments:
  path                  Repository or file path to scan

options:
  -h, --help            show this help message and exit
  --json                Emit the stable v1 JSON list
  --json-v2             Emit detailed JSON with scan metadata
  --max-findings MAX_FINDINGS
                        Maximum findings to print
  --max-file-bytes MAX_FILE_BYTES
                        Ignore file content larger than this byte count
  --fail-on-block       Exit 2 when BLOCK findings are present
  --fail-on {block,trim,flag}
                        Exit 2 at this decision threshold or higher
  --summary             Print aggregate scan counts
  --quiet               Suppress human-readable output and notices
  --exclude GLOB        Skip files whose repo-relative path matches GLOB
                        (repeatable)
  --no-default-excludes
                        Also scan default-excluded paths: .agents/*,
                        .claude/*, .codex/*, .cursor/*
```

Run a text scan:

```bash
python3 anti-slop/scripts/scan_repo_slop.py path/to/repo --summary
```

Run a machine-readable gate:

```bash
python3 anti-slop/scripts/scan_repo_slop.py path/to/repo --json-v2 --fail-on trim
```

Output contracts:

| Mode | Shape |
|---|---|
| `--json` | Stable v1 list with `path`, `line`, `code`, `severity`, `message`, and `excerpt` |
| `--json-v2` | Object with `schema_version`, detailed findings, truncation state, omitted count, and scan summary |

V2 findings add `rule_id`, `impact`, `decision`, and `fix`. Its summary reports files considered, files scanned, files skipped for size, unreadable files, total and returned findings, and counts by decision.

The default content limit is 4 MiB per file. Files above the limit still receive filename checks, but their content is not read. `--max-findings` limits reported findings after deterministic ordering; omitted findings are signaled in `stderr` and in JSON v2. `--quiet` suppresses human output and notices, while an explicitly selected JSON format is still written to `stdout`.

The default exclusions are `.agents/`, `.claude/`, `.codex/`, and `.cursor/`. Use `--no-default-excludes` to scan synchronized copies. In a Git worktree, the scanner asks Git for tracked and untracked non-ignored files. Without Git, it walks recognized text files.

Failure thresholds are inclusive:

| Threshold | Return 2 for |
|---|---|
| `block` | `BLOCK` |
| `trim` | `BLOCK` or `TRIM` |
| `flag` | `BLOCK`, `TRIM`, or `FLAG` |

`--fail-on-block` is the compatibility form of `--fail-on block`.

Scanner exit codes:

| Code | Meaning |
|---:|---|
| 0 | Scan completed and the requested threshold was not met |
| 1 | Input path or executable registry could not be used |
| 2 | Requested threshold was met; argument parsing also uses 2 for invalid CLI input |

## Claude Code Stop hook

[`anti-slop/hooks/anti-slop-stop.py`](anti-slop/hooks/anti-slop-stop.py) is optional and Claude-specific. It scans the response scope from the shared registry. When the Stop payload lacks response text, it reads at most the final 2 MiB of the transcript and extracts the last assistant message.

The hook reports at most five findings and states how many were omitted. It is advisory by default and emits `hookSpecificOutput.additionalContext`. Set `ANTI_SLOP_HOOK_BLOCK=1` to emit a blocking decision. Invalid input, missing transcripts, and registry errors fail open.

For a project install, merge [`anti-slop/hooks/hooks.example.json`](anti-slop/hooks/hooks.example.json) into the Claude Code settings used by the project. The command quotes `${CLAUDE_PROJECT_DIR}` so project paths containing spaces remain one argument.

For a user install, point the same command at the user-scoped hook path, for example:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/skills/anti-slop/hooks/anti-slop-stop.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

## Test

Run the unit suite and repository gate:

```bash
python -m unittest discover tests -v
python anti-slop/scripts/scan_repo_slop.py . --fail-on-block --quiet
```

CI runs the unit command and self-scan on Ubuntu with Python 3.9, 3.11, and 3.13, and on Windows with Python 3.11.

## Repository layout

```text
ai-antislop/
|-- .github/workflows/ci.yml
|-- LICENSE
|-- README.md
|-- anti-slop/
|   |-- SKILL.md
|   |-- rules/rules.json
|   |-- lib/anti_slop_engine.py
|   |-- references/
|   |-- scripts/
|   |   |-- scan_repo_slop.py
|   |   `-- sync_skill.py
|   |-- hooks/
|   |   |-- anti-slop-stop.py
|   |   `-- hooks.example.json
|   `-- evals/
`-- tests/
```

## License

[MIT](LICENSE)
