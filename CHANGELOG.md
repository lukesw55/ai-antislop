# Changelog

## Unreleased

### Changed

- The Stop hook's default output is now `systemMessage`, a warning shown to the user that does not make Claude continue. The previous default, `hookSpecificOutput.additionalContext`, continues the conversation according to the Claude Code hooks reference. Set `ANTI_SLOP_HOOK_MODE=context` to keep the previous behavior or `ANTI_SLOP_HOOK_MODE=block` for a blocking decision. `ANTI_SLOP_HOOK_BLOCK=1` still selects `block`. The `warn` text no longer asks the reader to revise before stopping, because its reader is the user.
- `S1-label-colon-bullet` is a `sequence` detector: it fires once per run of at least three consecutive label-colon bullets instead of on every bullet. Its id, code, impact, and decision are unchanged.
- Regex rules anchored at line start use `[ \t]` for indentation and accept CRLF line ends, and the engine attributes a match to its first non-blank character. Previously a match that began on a blank line was reported on that blank line with an empty excerpt, and the content line was never reported.
- `S2-verification-claim`, `D2-maturity-claim`, and `S3-attention-bait` declare same-line exclusions for conditionals and instructions ("if tests pass", "if all tests pass", "when the build passes", "ensure all tests pass"), explicit negations ("not production-ready", "isn't production-ready"), and the phrases "magic number" and "10x multiplier". The S3 exception is scoped to those two terms, so "shocking numbers" is still reported. Statements such as "production-ready in Chromium 126" remain findings by design; a version number is not evidence.
- The scanner's text summary ends with `suppressed=N`. JSON v1 is unchanged. JSON v2 adds `summary.suppressed_findings`; `total_findings` keeps counting active findings.

### Added

- Rule fields `unless_preceded_by` and `unless_followed_by`, as a list that applies to every alternative of the pattern or as an object keyed by the matched text that applies to one alternative. Unknown registry keys are rejected when the registry loads.
- Inline suppressions in the scanner: `anti-slop-ignore-next-line RULE_ID -- reason` and `anti-slop-ignore-file RULE_ID -- reason`, as whole-line HTML, `#`, or `//` comments. The file form must appear within the first 10 lines. Invalid directives are reported on `stderr` and suppress nothing. The Stop hook does not honor directives.
- `--rules PATH` on the scanner and `ANTI_SLOP_RULES` on the hook load a complete alternative registry without merging.
- `anti-slop/evals/rule-corpus.json`: 59 deterministic cases with exact rule, line, and decision expectations, run by `tests/test_eval_corpus.py`, which also requires a positive and a negative case for every rule.
- Response patterns C10 to C13 (portable sentences, unverifiable attribution, synonym cycling, artificial kicker) and a Preserve section in `anti-slop/references/response-patterns.md`.
- README sections for the one-command install, the registry format, inline suppressions, hook modes, and limitations.

### Verification record

Scanner counts on four public repositories with default options and `--json-v2 --quiet --max-findings 100000`, grouped by rule id. "Before" is this repository at `d1f499a`; "after" is the head that carries the changes above. Zero is not the goal: remaining findings are candidates for human review, and these repositories are not part of CI.

| Repository | Commit | Before | After |
|---|---|---|---|
| Nutlope/hallmark | `13ac0ec` | 219: 202 S1-label-colon-bullet, 11 D2-polish-word, 4 S3-attention-bait, 2 D2-maturity-claim | 52: 36, 11, 3, 2 |
| peteromallet/desloppify | `3a7735d` | 23: 9 S1-label-colon-bullet, 5 D2-polish-word, 4 S3-attention-bait, 3 S2-verification-claim, 2 D5-generated-media-provenance | 11: 1, 5, 3, 0, 2 |
| petergyang/no-ai-slop | `000650b` | 1: D2-polish-word on a list of banned words | 1: unchanged |
| hardikpandya/stop-slop | `8da1f03` | 0 | 0 |

The three `S2-verification-claim` BLOCK findings on desloppify were the instruction "If tests pass, commit:"; none remain. The two `D2-maturity-claim` findings on hallmark are statements about browser support phrased as "production-ready in ..."; they remain findings and can be suppressed inline with a reason.

Hook modes exercised on 2026-09-15 in Claude Code 2.1.272 with a project-level Stop hook and `--output-format stream-json`: `warn` surfaced the message as a notice and the turn ended; `context` and `block` each produced one revised response, after which the second Stop invocation saw `stop_hook_active` and stayed silent.

Installation exercised on 2026-09-15 with `npx skills add <clone> --skill anti-slop -a claude-code -y` (skills CLI 1.5.26) in an empty project: the whole `anti-slop/` tree was copied to `.claude/skills/anti-slop/`, the installed scanner loaded its registry, and no hook was enabled.

Unit suite: 84 tests on Python 3.11.15 locally; CI covers Python 3.9, 3.11, and 3.13 on Ubuntu and 3.11 on Windows.
