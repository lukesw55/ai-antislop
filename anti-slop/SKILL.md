---
name: anti-slop
description: Detect, classify, gate, and rewrite AI-shaped repository output without losing behavior or evidence. Use when writing or reviewing code, documentation, README text, PRs, issues, changelogs, generated artifacts, media metadata, or assistant responses that may affect a repository, especially when the user asks to remove AI slop, boilerplate, generic phrasing, unsupported claims, fake polish, or unnecessary structure.
---

# Anti-slop

Apply a portable repository-quality protocol for Claude Code, Codex, and Cursor. Preserve facts and behavior while removing unsupported claims, generic structure, fake maturity signals, and artifacts without a current purpose.

Do not assume that any runtime activates this skill automatically. Apply it when the runtime loads it or the user invokes it.

## Keep the architecture portable

- Treat this `SKILL.md` as the shared workflow contract.
- Treat `rules/rules.json` as the single source of truth for executable detectors and their metadata.
- Keep runtime-specific commands out of the core protocol.
- Synchronize the skill to `.claude/skills/anti-slop/`, `.agents/skills/anti-slop/`, or legacy `.codex/skills/anti-slop/` as required by the host.
- Generate `.cursor/rules/antislop.mdc` with minimal MDC frontmatter by default.
- Use `--cursor-body-only` only for a manual body-only mapping without frontmatter.
- Treat synchronized copies as generated targets; change the canonical source and registry instead.

## Preserve what matters

1. Preserve behavior, contracts, evidence, constraints, edge cases, security checks, citations, and operational detail.
2. Remove generic framing, decorative structure, unsupported claims, invented APIs, fake results, and fake maturity signals.
3. Create files, abstractions, wrappers, configuration, and documentation only when they serve a current repository need.
4. Keep validation at real boundaries such as user input, public APIs, filesystems, networks, authentication, payments, migrations, and serialization.
5. Replace broad praise with repository-grounded facts or an explicit assumption.
6. Prefer the smallest complete change, not the shortest text.
7. Keep verbose material when removing it would erase a decision, invariant, recovery step, or compatibility constraint.

## Select one mode

- **Gate mode**: Clean new output before delivery. Rewrite the draft, not unrelated repository content.
- **Sweep mode**: Audit existing files. Keep the audit read-only unless the user separately requests edits.
- **Diff mode**: Review a patch or PR. Keep the review read-only unless the user separately requests fixes.

Never edit while performing a read-only audit. Finish the findings first, then enter an explicit rewrite phase if authorized.

## Follow the required flow

Use this sequence without skipping a gate:

`Context -> Detect -> Classify -> Gate -> Rewrite -> Verify -> Deliver`

### 1. Context

- Identify the requested mode, audience, artifact, repository conventions, and allowed scope.
- Locate evidence for claims about behavior, compatibility, tests, performance, security, releases, dependencies, and generated assets.
- Mark missing evidence before changing wording.
- Load only the references needed for the artifact under review.

### 2. Detect

Keep deterministic detection separate from semantic judgment.

For deterministic detection:

- Read executable patterns and metadata from `rules/rules.json`.
- Record exact paths, lines, rule IDs, and matched text when available.
- Treat a pattern match as a candidate, not proof of slop.
- Use `scripts/scan_repo_slop.py` only when a static repository scan helps. Keep it read-only; use its existing `--fail-on-block` behavior only when a failing gate was requested.

For semantic detection:

- Check whether each claim follows from code, source material, tool output, or a cited source.
- Check whether structure helps a maintainer act or merely makes the artifact look finished.
- Check whether abstractions have current callers and whether files have a durable repository purpose.
- Check whether a proposed simplification removes behavior, error handling, or load-bearing context.
- Explain semantic findings from evidence; do not encode subjective prose judgments as pretend-deterministic rules.

### 3. Classify

Tag each finding with a slop class, an impact, and a decision. Keep impact and decision in separate fields.

Use these classes:

- **S1 formulaic/generic**: Template-shaped prose, predictable framing, boilerplate names, or decorative structure.
- **S2 false/inconsistent**: Invented APIs, fake results, unsupported claims, contradictions, or claims beyond the evidence.
- **S3 attention-bait**: Exaggerated, manipulative, or engagement-optimized wording.
- **S4 workplace distraction**: Polished output that creates review or maintenance work without adding useful information.

Assign impact by cost if shipped:

- **critical**: Can mislead operation, security, compatibility, data handling, or release decisions.
- **major**: Can cause incorrect implementation, substantial review work, or lasting repository clutter.
- **minor**: Reduces clarity or adds local noise without changing decisions or behavior.

Assign a separate decision for the current task:

- **BLOCK**: Require removal, correction, or verified evidence before delivery.
- **TRIM**: Rewrite or reduce while preserving the useful content.
- **FLAG**: Report the concern without blocking by default.
- **IGNORE**: Keep it because context justifies it or the match is a false positive.

Use `S2 | critical | BLOCK`, not a combined severity label. Default critical findings to `BLOCK`, major findings to `BLOCK` or `TRIM`, and minor findings to `TRIM` or `FLAG`; override a default only with a stated contextual reason.

### 4. Gate

Return `PASS` or `FAIL` for every applicable gate:

- **Evidence gate**: Pass only when factual claims are supported, cited, or clearly marked as assumptions.
- **Behavior gate**: Pass only when the rewrite preserves observable behavior, contracts, boundaries, and required context.
- **Contamination gate**: Pass only when each new artifact or abstraction has a current repository purpose.
- **Delivery gate**: Pass only when no `critical` finding and no `BLOCK` or `TRIM` decision remains unresolved.

In Gate mode, deliver only after all applicable gates pass. In Sweep and Diff modes, report failed gates without modifying files.

### 5. Rewrite

- Rewrite only in Gate mode or after explicit authorization to edit audited material.
- Make the smallest change that resolves the finding.
- Preserve APIs, control flow, error behavior, security boundaries, citations, examples required for use, and verified facts.
- Replace unsupported certainty with a narrower fact, an attributed source, or an explicit uncertainty.
- Remove an artifact only after confirming that it has no current caller, contract, or operational purpose.
- Do not change code behavior merely to make it shorter or less defensive.

### 6. Verify

- Compare the result with the source and confirm that every resolved finding changed for the stated reason.
- Re-run relevant deterministic detection when available; treat a clean scan as evidence only for the rules it covers.
- Run other checks only when available and appropriate to the task. Report the exact check and result; never imply that a test, build, scan, or hook ran when it did not.
- Re-evaluate all four gates after rewriting.
- Perform a short self-critique: Did I remove evidence? Did I change behavior? Did I invent a claim? Did I create new review work? Fix any `yes` before delivery.

### 7. Deliver

- Deliver the cleaned artifact directly in Gate mode.
- Deliver findings and gate results in Sweep mode; offer rewrites without applying them unless edits were requested.
- Deliver one actionable finding per location in Diff mode; include justified `Keep` items when verbose content is load-bearing.
- State what remains unverified and provide a lower-claim alternative when evidence is unavailable.
- Keep logs factual and compact. Distinguish commands run, observed results, and inferences.

## Load references by need

- Load `references/slop-taxonomy.md` for ambiguous classes, impact, decisions, or false positives.
- Load `references/repo-contamination.md` for file trees, scaffolding, generated files, README expansion, changelogs, or unsupported repository claims.
- Load `references/code-patterns.md` for code-specific findings and behavior-preserving rewrites.
- Load `references/docs-patterns.md` for README, documentation, PR, issue, ADR, changelog, and ticket text.
- Load `references/response-patterns.md` for assistant-response cleanup.
- Load `references/multimodal-patterns.md` for images, video, audio, captions, transcripts, alt text, or asset metadata.

Do not load every reference by default. Keep detailed patterns in their reference file rather than copying them into this protocol.

## Use optional automation carefully

- Use `scripts/scan_repo_slop.py` as a read-only candidate detector, not as a semantic judge or rewrite engine.
- Use `hooks/anti-slop-stop.py` only as an optional Claude Code hook. Review its configuration before installation and do not assume that it is installed or enabled.
- Keep scanner and hook decisions aligned through `rules/rules.json`; do not duplicate executable patterns in this file.

## Format audits consistently

For Sweep mode, use:

```text
path:line - S2 | critical | BLOCK - Unsupported compatibility claim.
Evidence: <observed source or missing evidence>
Safe rewrite: <proposed wording or action>
Gates: Evidence FAIL; Behavior PASS; Contamination PASS; Delivery FAIL
```

For Diff mode, use one concise line per finding:

```text
path:line - S1 | minor | TRIM - Remove generic framing; keep the constraint that follows.
Gates: Evidence PASS; Behavior PASS; Contamination PASS; Delivery FAIL
```

End every Sweep and Diff output with one `Gates:` line containing `Evidence`, `Behavior`, `Contamination`, and `Delivery`, each marked `PASS` or `FAIL`. Use `N/A (<brief reason>)` only when a gate is genuinely inapplicable; never omit a gate.

Add a `Keep` section only for material that resembles a pattern but preserves necessary context.
