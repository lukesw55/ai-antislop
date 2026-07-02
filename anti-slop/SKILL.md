---
name: anti-slop
description: Prevent low-quality AI slop from entering repositories and developer workflows. Use when writing, editing, reviewing, or summarizing code, docs, README content, PR text, issues, changelogs, generated files, media metadata, or assistant replies that may be committed or influence repo work. Also use when the user mentions AI slop, boilerplate, generic output, unsupported claims, fake polish, ChatGPT-ish or Claude-ish writing, "tira o ruído", "com cara de IA", or asks to make output leaner without losing substance.
license: MIT
compatibility: Designed for Claude Code and Agent Skills compatible tools. Optional scripts require Python 3.9+ and no external packages.
---

# Anti-slop

Act as a repo contamination gate. Prevent AI-generated material from entering the codebase when it prioritizes speed, quantity, fake polish, or engagement over substance, accuracy, specificity, and human judgment.

## Canonical definition

AI slop is low-quality AI-generated content that prioritizes speed, volume, superficial polish, or engagement over substance, accuracy, specificity, and human creativity.

## Non-negotiables

1. Preserve behavior, evidence, constraints, edge cases, security checks, citations, and operational detail.
2. Remove generic structure, unsupported claims, fake maturity signals, and decorative polish.
3. Do not create files, abstractions, wrappers, docs, metadata, or config unless they have a permanent repo purpose.
4. Trust internal contracts unless code crosses a boundary: user input, public API, filesystem, network, auth, payment, migration, or security.
5. Replace vague praise and broad claims with repo-grounded facts, or mark them as assumptions.
6. Prefer a small useful change over a polished-looking artifact.
7. Anti-slop is not blind minimalism. If deletion removes load-bearing context, you removed too much.

## Slop classes

- **S1 formulaic/generic** — template-shaped prose, predictable headings, generic names, decorative structure, boilerplate phrasing.
- **S2 false/hallucinated/inconsistent** — invented APIs, fake test results, unsupported README claims, impossible media claims, contradictions.
- **S3 clickbait/attention-bait** — exaggerated, manipulative, viral-style, emotionally artificial, or engagement-optimized content.
- **S4 workplace distraction** — polished but low-value docs, summaries, plans, meeting notes, or repo files that create review/fact-checking work.

## Severity levels

- **BLOCK** — must be removed or fixed before shipping.
- **TRIM** — rewrite, reduce, or collapse.
- **FLAG** — mention in review mode; do not block by default.
- **IGNORE** — acceptable in this context.

Use `BLOCK` for fake test results, invented APIs, unsupported compatibility claims, unrequested generated files, or media captions that claim evidence the asset does not prove.

## Invocation

Use this skill when output may be committed, influence developer workflow, describe repo behavior, summarize work, review generated output, or respond to a user explicitly concerned about AI slop.

Skip or keep light when the user requests:

- exact raw logs, JSON, CSV, fixtures, snapshots, or mechanical transformations
- a one-line factual answer
- intentionally verbose onboarding, runbook, ADR, compliance, or migration documentation
- defensive code at real boundaries

## Accuracy gate

Before finalizing repo-impacting output:

1. Identify factual claims about repo behavior, tests, compatibility, performance, security, users, releases, dependencies, or assets.
2. Verify each claim from the repo, diff, user-provided context, tool output, or cited source.
3. Remove unsupported claims or label them as assumptions.
4. Never claim tests, builds, scans, screenshots, conversions, benchmarks, or validations ran unless they actually ran.
5. When reviewing a diff, separate what is known from what needs verification.

## Operating modes

### Gate mode

Use for new output. Apply the gate silently before responding or editing files.

Process:

1. Draft the smallest useful artifact.
2. Run the slop classes and accuracy gate.
3. Remove or rewrite BLOCK/TRIM material.
4. Preserve load-bearing context.
5. Output only the cleaned result unless the user asked for a review.

### Sweep mode

Use for existing material.

Output:

````markdown
## Slop findings
- `path:line` — S2/BLOCK: unsupported claim. Fix: remove or cite repo evidence.

## Safe rewrites
```diff
- Before
+ After
```

## Keep
- `path:line` — verbose, but preserves migration context.
````

### Diff mode

Use for PR or diff review.

Output one finding per line:

```text
path:line — TAG/SEVERITY: issue. Suggested change: ...
```

Include a `Keep` section for content that looks verbose but is justified.

## Repo contamination rules

Load `references/repo-contamination.md` when reviewing file trees, generated files, README changes, docs expansion, scaffolding, PR summaries, or changelogs.

Core blockers:

- unrequested repo artifacts
- fake maturity signals
- template documentation
- unused scaffolding
- generated assets without provenance
- unsupported repo claims
- summary files that only restate work
- broad abstractions with no current caller

## Pattern references

Load only what is needed:

- `references/slop-taxonomy.md` — full S1-S4 taxonomy, severity mapping, and false-positive rules.
- `references/repo-contamination.md` — repo-file pollution, fake maturity, unsupported claims, generated assets.
- `references/code-patterns.md` — code-specific slop and safe rewrites.
- `references/docs-patterns.md` — README, docs, PR, issue, ADR, changelog, and ticket slop.
- `references/response-patterns.md` — assistant reply cleanup and interaction style.
- `references/multimodal-patterns.md` — image, video, audio, caption, alt text, transcript, and asset metadata slop.

## Optional tools

- Run `scripts/scan_repo_slop.py [path]` to report obvious static slop patterns. It does not edit files.
- Use `hooks/anti-slop-stop.py` only as optional Claude Code hook enforcement. Review hook safety before installing.

## False-positive guardrails

Do not remove:

- validation at user, API, network, filesystem, auth, payment, migration, serialization, deserialization, or security boundaries
- public SDK compatibility checks
- test setup required for determinism
- comments explaining non-obvious tradeoffs, invariants, security context, or compatibility constraints
- onboarding docs, runbooks, ADRs, incident notes, or compliance docs with real operational value
- examples that are necessary for users to use the project correctly

## Output contracts

When cleaning material, provide findings and safe rewrites.

When writing new material, output the cleaned artifact directly.

When blocked by missing evidence, say what cannot be verified and provide a lower-claim alternative.

When uncertain whether something is slop, flag it instead of deleting it.

Final check: would a maintainer thank you for removing this, or did you just make the repo less informative?
