# Slop Taxonomy

Use this reference when you need a repeatable classification instead of a style-only cleanup.

## S1 — Formulaic / generic

Signals:

- template headings that could apply to any repo
- label-colon bullet rhythm repeated across a section
- generic names: `data`, `manager`, `helper`, `processor`, `service`, `thing`
- prose that sounds polished but says nothing specific
- symmetry created for aesthetics rather than understanding
- emojis, badges, or decorative sections that do not change comprehension

Default severity: `TRIM`. Escalate to `BLOCK` when generic material creates a permanent repo artifact or masks a real limitation.

## S2 — False / hallucinated / inconsistent

Signals:

- claims not supported by code, diff, tests, logs, or user-provided context
- fake test/build/benchmark/security statements
- invented APIs, CLI flags, settings, integrations, file paths, or product behavior
- README or changelog claims that describe work not present in the repo
- contradictory instructions across docs
- media descriptions that claim evidence not visible or verified

Default severity: `BLOCK`.

## S3 — Clickbait / attention-bait

Signals:

- exaggerated claims: "revolutionary", "game-changing", "10x", "magic", "world-class"
- emotionally manipulative phrasing
- fake urgency or viral framing
- bizarre examples designed for attention rather than utility
- marketing copy in technical docs without evidence

Default severity: `TRIM`. Escalate to `BLOCK` if it misleads users.

## S4 — Workplace distraction

Signals:

- polished summaries that require more fact-checking than they save
- meeting notes, plans, or status files that repeat what is already in commits/issues
- implementation narratives stored as permanent docs
- "what I did" files created by the agent
- long PR descriptions that obscure the actual risk

Default severity: `TRIM` or `BLOCK` for unrequested permanent files.

## Severity mapping

| Severity | Use when | Action |
|---|---|---|
| BLOCK | false, unsupported, unrequested, misleading, or repo-polluting | remove, rewrite, or ask for evidence |
| TRIM | verbose, repetitive, generic, over-structured | compress or rewrite |
| FLAG | possible smell with context-dependent value | mention only in review mode |
| IGNORE | justified by boundary, compliance, onboarding, or explicit user request | preserve |

## Anti-slop is not minimalism

Do not remove load-bearing context. Preserve details that help maintainers make correct decisions:

- evidence and citations
- constraints and assumptions
- edge cases and failure modes
- security and privacy context
- compatibility requirements
- migration notes
- operational runbook steps
- public API examples

## Decision test

Ask:

1. Is this specific to this repo, user, diff, or asset?
2. Is it verified or clearly labeled as an assumption?
3. Does it help a maintainer act?
4. Would deleting it reduce correctness, safety, or operability?

If the answer to 1-3 is no and 4 is no, it is probably slop.
