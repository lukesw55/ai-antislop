# Documentation and Workflow Text Patterns

Use this when writing or reviewing README files, markdown docs, PR descriptions, issues, tickets, ADRs, changelogs, migration notes, and commit messages.

## B1 — Template sections

Slop:

```markdown
## Overview
This project provides a robust and comprehensive solution.

## Details
The implementation is designed to be flexible and scalable.

## Conclusion
This improves the overall experience.
```

Fix: replace with concrete install, usage, constraints, and maintenance facts.

## B2 — README that repeats the repo name

Slop:

```markdown
# auth-service

Auth Service is an auth service that provides authentication services.
```

Fix:

```markdown
# auth-service

Issues JWTs for internal APIs and validates session refresh tokens.
```

## B3 — Label-colon bullet rhythm

Slop:

```markdown
- **Simple:** Easy to use.
- **Powerful:** Supports many workflows.
- **Flexible:** Works in many situations.
```

Fix with specific facts or delete.

## B4 — Forced symmetry

Slop happens when sections are made equally sized even when the content does not justify it.

Fix: let the important section be longer and delete empty parallelism.

## B5 — Static metadata nobody maintains

Trim or remove:

- generated timestamps
- "last updated" without a maintenance process
- manual file counts
- manual compatibility tables not tested
- "status" labels with no source of truth

## B6 — Decorative emoji and badges

Remove decoration that does not improve scanning or trust.

Keep badges only when they point to real status: CI, package, coverage, license, docs, security policy.

## B7 — PR and commit slop

Slop:

- "This PR refactors the codebase to improve maintainability."
- "Implemented changes as requested."
- "Updated files and fixed issues."
- long summaries that do not name risks or behavior

Fix:

```markdown
Fix token refresh to reject expired sessions before issuing a new access token.

Risk: clients relying on expired refresh tokens now receive 401.
Verification: `pytest tests/auth/test_refresh.py`
```

Only claim verification that actually ran.

## B8 — ADR slop

ADRs may be long. Do not trim real tradeoffs.

Block:

- fake alternatives
- decisions without context
- "chosen for scalability" with no evidence
- generic consequences

Keep:

- constraints
- rejected options
- migration cost
- operational impact
- security and compatibility tradeoffs

## B9 — Changelog slop

Block changelog entries that are not tied to actual changes.

Prefer:

```markdown
- Reject expired refresh tokens before issuing new access tokens.
```

over:

```markdown
- Improved authentication system robustness and reliability.
```

## B10 — Ticket slop

Tickets should create action, not ambience.

Keep:

- problem
- scope
- acceptance criteria
- constraints
- verification

Delete:

- generic background
- motivational filler
- copied chat summaries
- "future enhancements" without owner or timeline
