# anti-slop

**A portable quality gate for code, docs, diffs, and agent responses that refuses to invent confidence.**

[Claude Code](https://code.claude.com/docs/en/skills) / [Codex](https://developers.openai.com/codex/skills) / [Cursor](https://cursor.com/docs/rules.md) / [Hallmark reference](https://github.com/Nutlope/hallmark)

anti-slop keeps useful detail and removes the signals that make generated work expensive to review: unsupported maturity claims, template-shaped prose, disposable repository files, and narration that adds no decision.

| 48 | 16 | 3 |
| ---: | ---: | ---: |
| semantic patterns in the catalog | executable registry detectors | review modes: Gate, Sweep, Diff |

The catalog is the context layer. The registry is the mechanical layer. Neither treats a match as proof by itself.

## Quick start

Install the skill into the current project with the `skills` CLI:

```bash
npx skills add lukesw55/ai-antislop --skill anti-slop
```

Add `-a claude-code`, `-a codex`, or `-a cursor` to choose a runtime, `-y` to skip prompts, and `-g` for a user-level install. The CLI copies the whole `anti-slop/` tree: `SKILL.md`, references, the rule registry, the engine, the scanner, the hook, and the eval corpus. It does not enable the hook. From a local clone the same command accepts a path:

```bash
npx skills add ./ai-antislop --skill anti-slop -a claude-code -y
```

Invoke the skill by name when the review matters:

| Runtime | Example request |
|---|---|
| Claude Code | `Use the anti-slop skill in Sweep mode on README.md.` |
| Codex | `$anti-slop Review the current diff in Diff mode.` |
| Cursor | `Apply anti-slop in Gate mode to this change.` |

Runtime discovery can vary by version and configuration; this repository does not promise deterministic automatic activation.

Run the read-only scanner from an installed copy (adjust the prefix for `.agents/skills/` installs):

```bash
python3 .claude/skills/anti-slop/scripts/scan_repo_slop.py . --summary
```

The bundled `sync_skill.py` script is the alternative for installs without Node, for the Cursor rule adapter, and for drift checks. See [Synchronize with the bundled script](#synchronize-with-the-bundled-script).

## What it does

| Surface | Typical question | Default action |
|---|---|---|
| Code and docs | Is this structure necessary, supported, and maintained? | Preserve behavior; trim ceremony. |
| Repository artifacts | Does this file have a current caller, owner, or durable purpose? | Remove residue; keep operational context. |
| Assistant responses | Is this claim evidenced, or is it just confident wording? | State the verified result and its limits. |
| Media and metadata | Can the source, provenance, and scope be checked? | Record provenance; narrow the claim. |

The scanner is read-only. The skill can rewrite when the selected mode and user scope authorize it.

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

The reference catalog contains 48 semantic patterns. Agents use these patterns with repository context; they are not all regular expressions.

| Surface | IDs | Count |
|---|---|---:|
| Code | A1-A10 | 10 |
| Documentation | B1-B10 | 10 |
| Assistant responses | C1-C13 | 13 |
| Repository contamination | D1-D8 | 8 |
| Multimodal material | M1-M7 | 7 |

The executable registry contains 16 deterministic detectors: 5 filename rules, 10 regex rules, and 1 sequence rule. [`anti-slop/rules/rules.json`](anti-slop/rules/rules.json) is the source of truth for those detectors. [`anti-slop/lib/anti_slop_engine.py`](anti-slop/lib/anti_slop_engine.py) loads the registry and is shared by the scanner and hook.

A deterministic match is a candidate finding. Semantic claims, behavior preservation, and false positives still require context. Detailed guidance lives in [`anti-slop/references/`](anti-slop/references/) and is loaded only when needed.

### Registry format

Every rule has `id`, `code`, `impact`, `decision`, `scopes`, `kind`, `message`, and `fix`. The `kind` field selects the detector:

| Kind | Fields | Behavior |
|---|---|---|
| `filename` | `filenames` | Reports a file whose name is in the list, at line 1 |
| `regex` | `pattern`, `flags` | Reports each line where the pattern matches; `flags` may include `IGNORECASE`, `MULTILINE`, `DOTALL` |
| `sequence` | `line_pattern`, `min_consecutive`, `flags` | Reports one finding at the first line of a run of at least `min_consecutive` consecutive matching lines; only `IGNORECASE` is allowed |

`regex` and `sequence` rules may also declare `unless_preceded_by` and `unless_followed_by`: lists of regex fragments, compiled case-insensitively, checked against the word immediately before or after the match on the same line. Markdown emphasis markers between them are ignored. The registry uses these fields to skip conditionals such as "if tests pass", explicit negations such as "not production-ready", and the technical phrases "magic number" and "10x multiplier". An exclusion applies to every alternative in the rule's pattern. Unknown keys are rejected when the registry loads.

Matches inside quotes, backticks, and Markdown code fences are never reported. A pattern anchored at line start should use `[ \t]` for indentation and `\r?$` before an end anchor so CRLF files report the right line; the engine also attributes a match to its first non-blank character.

## Static scanner

[`anti-slop/scripts/scan_repo_slop.py`](anti-slop/scripts/scan_repo_slop.py) is dependency-free and read-only. Its current help is:

```text
usage: scan_repo_slop.py [-h] [--json | --json-v2]
                         [--max-findings MAX_FINDINGS]
                         [--max-file-bytes MAX_FILE_BYTES] [--fail-on-block]
                         [--fail-on {block,trim,flag}] [--summary] [--quiet]
                         [--exclude GLOB] [--no-default-excludes]
                         [--rules PATH]
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
  --rules PATH          Load this complete rule registry instead of the
                        bundled rules.json
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

V2 findings add `rule_id`, `impact`, `decision`, and `fix`. Its summary reports files considered, files scanned, files skipped for size, unreadable files, total and returned findings, suppressed findings, and counts by decision. `total_findings` counts active findings only.

The default content limit is 4 MiB per file. Files above the limit still receive filename checks, but their content is not read. `--max-findings` limits reported findings after deterministic ordering; omitted findings are signaled in `stderr` and in JSON v2. `--quiet` suppresses human output and notices, while an explicitly selected JSON format is still written to `stdout`.

The default exclusions are `.agents/`, `.claude/`, `.codex/`, and `.cursor/`. Use `--no-default-excludes` to scan synchronized copies. In a Git worktree, the scanner asks Git for tracked and untracked non-ignored files. Without Git, it walks recognized text files.

`--rules PATH` replaces the bundled registry with a complete alternative file in the same format. There is no merging. A missing or invalid registry exits 1.

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

## Inline suppressions

A repository can keep a legitimate match without loosening the rule. Two directives are recognized when the whole line is a comment in HTML, `#`, or `//` form, and each requires a reason after `--`:

```text
<!-- anti-slop-ignore-next-line S2-verification-claim -- quotes the CI policy, not a result -->
<!-- anti-slop-ignore-file D7-summary-file -- mdBook table of contents -->
```

| Directive | Scope | Placement |
|---|---|---|
| `anti-slop-ignore-next-line RULE_ID -- reason` | That rule on the line immediately after the directive | Anywhere |
| `anti-slop-ignore-file RULE_ID -- reason` | That rule anywhere in the file, filename rules included | Within the first 10 lines |

Only exact rule ids are accepted; there are no wildcards or ranges. Suppression is applied per file before ordering, `--max-findings`, and `--fail-on` thresholds, so a suppressed `BLOCK` no longer fails a gate. Suppressed findings are counted in the JSON v2 summary and in the text summary. The directive line itself is not scanned, so a reason may quote the phrase it justifies.

An invalid directive prints `warning: <path>:<line>: anti-slop directive ignored: <reason>` on `stderr` and suppresses nothing. Causes: unknown rule id, missing reason, an HTML comment without `-->` on the same line, a file directive after line 10, or a next-line directive on the last line. `--quiet` silences these warnings. Directives inside Markdown code fences are treated as examples and ignored. In Markdown, prefer the HTML comment form; a `#` line renders as a heading.

The Stop hook never honors directives, so a response cannot dismiss its own review.

## Claude Code Stop hook

[`anti-slop/hooks/anti-slop-stop.py`](anti-slop/hooks/anti-slop-stop.py) is optional and Claude-specific. It scans the response scope from the shared registry. When the Stop payload lacks response text, it reads at most the final 2 MiB of the transcript and extracts the last assistant message. It reports at most five findings and states how many were omitted. Invalid input, missing transcripts, and registry errors fail open.

`ANTI_SLOP_HOOK_MODE` selects what the hook emits:

| Mode | Output | Effect in Claude Code |
|---|---|---|
| `warn` (default) | `systemMessage` | A warning is shown to the user. The turn ends. |
| `context` | `hookSpecificOutput.additionalContext` | Claude receives the findings as hook feedback and continues the turn to act on them. |
| `block` | `decision: "block"` with `reason` | Claude receives the findings as a blocking reason and continues the turn. |

`context` and `block` follow the same loop protections described in the [Claude Code hooks reference](https://code.claude.com/docs/en/hooks): the hook stays silent when `stop_hook_active` is set, and Claude Code caps consecutive continuations. `ANTI_SLOP_HOOK_BLOCK=1` is kept as an alias for `block`; a valid `ANTI_SLOP_HOOK_MODE` takes precedence over it. `ANTI_SLOP_RULES` points the hook at an alternative registry; an unreadable registry makes the hook exit silently.

The three modes were exercised in Claude Code 2.1.272 on 2026-09-15; the record is in [`CHANGELOG.md`](CHANGELOG.md).

For a project install, merge [`anti-slop/hooks/hooks.example.json`](anti-slop/hooks/hooks.example.json) into the Claude Code settings used by the project. The command quotes `${CLAUDE_PROJECT_DIR}` so project paths containing spaces remain one argument. Environment variables go in the `env` block of the same settings file or in the shell that starts Claude Code.

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

## Limitations

- A mechanical `BLOCK` is the configured policy for a pattern, not proof that the text is false. Review candidates before acting on them.
- The executable detectors match English phrasing. The Portuguese triggers in the response reference say when to apply the skill; they do not extend detection to Portuguese text.
- An `unless_*` exclusion applies to every alternative in a rule's pattern, not only to the alternative it was written for.
- Files above `--max-file-bytes` are not read, so file-level directives in them are not honored; their filename findings still apply.
- YAML frontmatter counts toward the 10-line limit for `anti-slop-ignore-file`.
- The semantic patterns in the references are applied by the agent. The unit tests and the rule corpus measure the deterministic layer only.

## Synchronize with the bundled script

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

The same `SKILL.md`, references, and executable registry are copied to Claude and Agent Skill targets. The Cursor adapter rewrites reference paths to the `.agents` installation.

## Test

Run the unit suite and repository gate:

```bash
python -m unittest discover tests -v
python anti-slop/scripts/scan_repo_slop.py . --fail-on-block --quiet
```

The suite includes [`anti-slop/evals/rule-corpus.json`](anti-slop/evals/rule-corpus.json), deterministic cases with exact rule, line, and decision expectations for every registry rule. [`anti-slop/evals/evals.json`](anti-slop/evals/evals.json) holds semantic scenarios for manual evaluation; they are not run automatically.

CI runs the unit command and self-scan on Ubuntu with Python 3.9, 3.11, and 3.13, and on Windows with Python 3.11.

## Repository layout

```text
ai-antislop/
|-- .github/workflows/ci.yml
|-- CHANGELOG.md
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
|       |-- evals.json
|       |-- rule-corpus.json
|       `-- trigger-queries.json
`-- tests/
```

## License

[MIT](LICENSE)
