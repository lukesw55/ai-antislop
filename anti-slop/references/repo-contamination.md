# Repo Contamination Rules

Use this when reviewing file trees, generated artifacts, docs expansion, scaffolding, PR summaries, or claims about repo state.

## D1 — Unrequested repo artifact

Block files created only because the agent wanted to show progress.

Examples:

- `SUMMARY.md`
- `PLAN.md`
- `IMPLEMENTATION.md`
- `NOTES.md`
- `CHANGES.md` outside an intentional changelog system
- generated "review report" files not requested by the user

Fix: delete the file or move useful content into the actual target document.

## D2 — Fake maturity signal

Block or trim badges, claims, or labels that imply maturity not shown in the repo.

Examples:

- "production-ready"
- "enterprise-grade"
- "battle-tested"
- "secure by default"
- "fully automated"
- "comprehensive test coverage"
- badges for CI, coverage, version, docs, license, or package status that are absent or unverified

Fix: replace with concrete facts, or remove.

## D3 — Template documentation

Trim docs that follow a generic scaffold without repo-specific substance.

Signals:

- "Overview / Features / Getting Started / Conclusion" with generic text
- feature lists that restate filenames
- duplicate installation paths
- empty "Architecture" sections
- "Next steps" sections that do not create action

Fix: keep only installation, usage, constraints, and examples users need.

## D4 — Unused scaffolding

Block code or config that has no current caller or runtime path.

Examples:

- helper modules with one call site
- interfaces for a single implementation
- plugin/config files not loaded by the project
- generic adapters for future providers
- `.env.example` values not used by code
- empty directories created for imagined future work

Fix: inline, delete, or add only when a real caller exists.

## D5 — Generated asset without provenance

Flag or block assets that may be AI-generated but lack context.

Examples:

- image prompts committed without purpose
- screenshots that are not reproducible
- synthetic audio/video transcripts without source metadata
- captions that claim facts from an unverified asset
- demo media with clickbait framing

Fix: add provenance, intended use, generation settings if relevant, and limitations; otherwise remove.

## D6 — Unsupported repo claim

Block statements that describe repo behavior without evidence.

Examples:

- "tests pass"
- "supports Windows"
- "handles all edge cases"
- "improves performance"
- "fixes security issues"
- "backward compatible"

Fix: cite the file, test output, commit, issue, benchmark, or mark as assumption.

## D7 — Summary file that only restates work

Block artifacts whose only value is "I completed X".

Fix: summarize in the chat reply or PR description, not as a permanent repo file.

## D8 — Broad abstraction with no current caller

Block abstractions added for hypothetical future needs.

Examples:

- `BaseService`
- `ProviderFactory`
- `AbstractManager`
- `ConfigurableStrategy`
- adapters for providers not supported today

Fix: implement the concrete path first. Extract when there are at least two real callers or a clear boundary.

## Permanent-file test

A new file earns its place only if at least one is true:

- imported, executed, or loaded by the repo
- used by the documented install or runtime path
- required by a public standard
- explicitly requested by the user
- needed as durable reference material for maintainers
