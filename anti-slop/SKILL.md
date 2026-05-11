---
name: anti-slop
description: Detect and remove AI slop from Claude Code outputs before they reach the repo or the user. Use before writing or editing code, comments, docstrings, markdown docs, README sections, PR descriptions, Jira/Linear tickets, ADRs, plans, or chat replies longer than two sentences. Also use when reviewing diffs, PRs, generated files, or anything the user calls "AI-generated", "slop", "too verbose", "boilerplate", "generic", "ChatGPT-ish", "Claude-ish", "com cara de IA", "tá com slop", or "tira o ruído". Pairs with humanizer for prose, impeccable for visual design, and Stop hooks for runtime enforcement.
---

# Anti-slop

Remove AI tells from code, comments, docs, repo structure, PR text, and Claude Code replies.

This skill is a **gate**, not a writing style guide. Use it before producing or modifying anything that might enter the codebase or a developer workflow.

## Non-negotiables

1. Ship the smallest useful change.
2. Trust internal contracts unless a boundary is involved.
3. Delete generic structure instead of polishing it.
4. Do not create files the user did not ask for.
5. Do not narrate obvious tool use.
6. Do not add abstractions for hypothetical reuse.
7. Preserve substance while removing slop.

If removing "AI slop" removes evidence, behavior, constraints, or useful context, you removed too much.

## When to invoke

Invoke before:

- writing or editing code
- adding comments or docstrings
- creating or expanding markdown docs
- drafting README, PR, ADR, issue, ticket, changelog, or migration text
- reviewing a diff or generated file
- responding with more than two sentences and any structured format
- creating any new file that was not explicitly requested
- adding defensive checks, helper functions, interfaces, wrappers, logs, or config

Invoke when the user says:

- remove AI slop
- kill the slop
- clean this up
- less verbose
- make it leaner
- this looks AI-generated
- review for AI tells
- corta o boilerplate
- tira o ruído
- tá com cara de ChatGPT
- esse código tá com slop
- essa resposta tá com cara de IA

Skip only when:

- returning raw logs, JSON, CSV, terminal output, or machine-readable data
- answering with one factual sentence
- making a tiny mechanical edit the user already specified exactly
- the user explicitly asks for a verbose, template-heavy, or defensive style

## Operating modes

### 1. Gate mode

Use when creating new output.

Apply the catalogue silently. The user should only see the lean result.

Before final output, ask internally:

> What still makes this look AI-generated?

Then remove that tell unless it is load-bearing.

### 2. Sweep mode

Use when reviewing existing material.

Return:

`````markdown
## Findings
- path:line — TAG short issue

## Rewrites
```diff
...
```

## Remaining smell

One sentence naming what still feels AI-generated, or `None`.
`````

Do not rewrite the whole file unless the user asked.

### 3. Diff mode

Use when reviewing code changes.

Prioritize comments that change behavior, reduce risk, or delete needless code. Avoid taste-only comments unless the slop is obvious.

Format:

```markdown
- `path:line` — TAG issue. Suggested change: ...
```

## Code slop catalogue

### A1. Boundary confusion

Slop:

```python
def total(items: list[Order]) -> float:
    if items is None:
        return 0.0
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    return sum(o.amount for o in items if o is not None)
```

Fix:

```python
def total(items: list[Order]) -> float:
    return sum(o.amount for o in items)
```

Rule: validate user input, network payloads, file contents, env vars, and external APIs. Trust internal typed callers.

### A2. Try/except that cannot recover

Slop:

```python
try:
    payload = json.loads(raw)
except Exception as exc:
    logger.error("Failed to parse payload: %s", exc)
    payload = {}
```

Fix:

```python
payload = json.loads(raw)
```

Rule: catch only specific exceptions and only when the code can recover correctly.

### A3. Single-use abstraction

Slop:

```ts
const DEFAULT_TIMEOUT_MS = 30000;

function createClient() {
  return new Client({ timeout: DEFAULT_TIMEOUT_MS });
}

const client = createClient();
```

Fix:

```ts
const client = new Client({ timeout: 30_000 });
```

Rule: extract after real reuse, not imagined reuse.

### A4. Generic names

Slop names:

```text
data
result
temp
final
info
payloadData
processData
handleResult
DataManager
Helper
Utils
Service
```

Fix by naming the domain object:

```text
pendingInvoices
signedPayload
expiredSessions
normaliseOrders
issueRefund
```

Rule: name what it is or what domain action it performs.

### A5. Comments that restate code

Slop:

```ts
// Loop through users and send each one an email
for (const user of users) {
  sendWelcomeEmail(user);
}
```

Fix:

```ts
for (const user of users) {
  sendWelcomeEmail(user);
}
```

Keep comments only for non-obvious constraints:

```ts
// Stripe retries this webhook for 72 hours, so this must stay idempotent.
await recordWebhookOnce(event.id);
```

### A6. Narration logs

Slop:

```ts
logger.info("Starting user creation");
const user = await createUser(input);
logger.info("Sending welcome email");
await sendWelcomeEmail(user);
logger.info("Finished user creation");
```

Fix:

```ts
const user = await createUser(input);
await sendWelcomeEmail(user);
```

Rule: log production-relevant facts, not a transcript of the function.

### A7. Premature configurability

Slop:

```ts
function fetchUser(id: string, timeout = 30000, retries = 3, backoff = 2, jitter = true) {
  ...
}
```

Fix:

```ts
function fetchUser(id: string) {
  ...
}
```

Rule: add parameters when a real caller needs different behavior.

### A8. Dead compatibility

Slop:

```ts
export function normaliseOrders(orders: Order[]) {
  ...
}

// Deprecated alias, kept for compatibility.
export const processData = normaliseOrders;
```

Fix:

```ts
export function normaliseOrders(orders: Order[]) {
  ...
}
```

Rule: compatibility is for released public contracts, not local renames.

### A9. Type/interface inflation

Slop:

```ts
interface CreateUserRequest {
  email: string;
  name: string;
}

async function createUser(req: CreateUserRequest) {
  return api.post("/users", req);
}
```

Fix:

```ts
async function createUser(req: { email: string; name: string }) {
  return api.post("/users", req);
}
```

Rule: named types must be reused, exported, or domain-meaningful.

### A10. Banners and artificial regions

Slop:

```ts
// =====================
// Helpers
// =====================
```

Fix: delete it.

Rule: if a file needs banners to be readable, split the file or improve names.

## Documentation slop catalogue

### B1. Template sections

Slop:

```markdown
## Overview
## Details
## Conclusion
```

Fix with load-bearing sections:

```markdown
## What changed
## Why it changed
## Risk
## Rollback
```

Rule: a heading should say something specific about this artifact.

### B2. README that repeats the repo name

Slop:

```markdown
# auth-service

This service handles authentication.
```

Fix:

```markdown
# auth-service

OIDC issuer in front of Keycloak. Validates device JWTs and issues short-lived API tokens.
```

Rule: start with what `ls`, the repo name, and the folder name cannot tell you.

### B3. Label-colon bullets

Slop:

```markdown
- **Speed:** faster page loads
- **Reliability:** fewer errors
- **Cost:** lower bills
```

Fix:

```markdown
- p95 page load dropped from 1.8s to 600ms
- 500 rate fell from 0.3% to 0.05%
- egress is down about $400/month
```

Rule: replace categories with evidence.

### B4. Forced symmetry

Slop: three pros, three cons, three risks, three next steps when only two are real.

Fix: keep the real count.

Rule: reality is usually uneven.

### B5. Static metadata nobody maintains

Slop:

```markdown
Status: Active
Last updated: 2026-05-08
Owner: TBD
```

Fix: delete unless a process keeps it accurate.

### B6. Decorative emoji

Slop:

```markdown
## 🚀 Launch
## ✅ Next steps
```

Fix:

```markdown
## Launch
## Next steps
```

Rule: use emoji only when the surrounding project already uses it.

## Claude Code reply slop catalogue

`.claude/hooks/scope-bloat-gate.sh` (Stop hook) already auto-blocks the loudest reply tells once per turn — em-dash density, label-colon runs of 4+, headings on short prompts, dual-question closes ("...? Or...?"), and scope bloat (response >5× prompt length without a doc keyword). The patterns below are the ones the hook does not catch — apply by hand.

### C1. Restating the prompt

Slop:

```text
You're asking me to rename this variable. I can help with that.
```

Fix: do the edit or answer directly.

### C2. Tool narration

Slop:

```text
I'll inspect the file, then identify the issue, then make the change.
```

Fix: call the tool. Report findings only when they matter.

Use a plan only for multi-step, ambiguous, or risky work.

### C3. Sycophantic openers

Delete:

```text
Great question.
Excellent point.
You're absolutely right.
Sure thing.
```

Start with the answer.

### C4. Trailing summaries

Slop:

```markdown
## Summary
I updated X, changed Y, and verified Z.
```

Fix:

```text
Done — updated `auth.ts`.
```

### C5. Follow-up spam

Slop:

```text
Want me to also add tests, update docs, refactor the caller, and open a PR?
```

Fix:

```text
Done.
```

Offer a follow-up only when the next step is genuinely ambiguous and high-value.

### C6. Over-structured small answers

If the answer is under six sentences, avoid headings, numbered plans, and tables unless the user asked.

## File artifact rules

Never create these unless the user explicitly asks:

```text
PLAN.md
NOTES.md
IMPLEMENTATION.md
SUMMARY.md
CHANGES.md
ANALYSIS.md
TODO.md
```

Do not create ADRs for reversible implementation details.

Do not add README sections such as Contributing, Roadmap, License, Code of Conduct, Architecture, or Table of Contents unless the repo actually needs them.

The right place for a change explanation is usually the PR body or commit message, not a parallel markdown file.

## Claude Code workflow

Before editing:

1. Identify the smallest file set needed.
2. Check existing style before adding new patterns.
3. Prefer deletion over abstraction.
4. Prefer direct code over wrappers.
5. Prefer existing tests over new scaffolding.

During editing:

1. Avoid broad rewrites.
2. Avoid opportunistic cleanup outside the requested scope.
3. Do not introduce new dependencies for formatting or convenience.
4. Do not create helper files unless required by the requested change.
5. Keep names domain-specific.

After editing:

1. Re-read the diff.
2. Remove any code that exists only because an AI would "be safe".
3. Remove comments that explain obvious code.
4. Remove generic docs, summaries, and headings.
5. Verify the change still preserves the user's requested behavior.

## Review checklist

Use this checklist internally:

```text
[ ] Did I add a guard for something an internal contract already guarantees?
[ ] Did I catch an exception without real recovery?
[ ] Did I create a helper, class, interface, constant, or config with one use?
[ ] Did I add a comment that restates code?
[ ] Did I use generic names like data/result/helper/manager?
[ ] Did I add logs that narrate execution?
[ ] Did I create a doc/file the user did not request?
[ ] Did I add headings, bullets, or symmetry because the output looked nicer?
[ ] Did I end with a summary or follow-up offer the user does not need?
[ ] Did I remove substance while removing slop?
```

## Output contracts

### When asked to clean existing material

Return only:

`````markdown
## Findings
- `path:line` — TAG issue

## Rewrites
```diff
...
```

## Remaining smell

None.
`````

### When asked to write new material

Return the clean artifact only. Do not explain that anti-slop was applied.

### When asked to review a PR or diff

Return concise review comments. Prefer:

```markdown
- `src/foo.ts:42` — A2 try/except without recovery. Let this throw or catch the specific error at the boundary.
```

Avoid:

```markdown
This code is generally good, but here are some suggestions...
```

## Interaction with other skills

Use `humanizer` for prose-heavy artifacts: emails, memos, narrative docs, customer comms, Slack messages, Confluence pages.

For prose that ships outbound (Confluence / Slack / customer / leadership), `humanize-deliverables` adds a hard sha256 gate on top of `humanizer` — `.claude/hooks/humanize-gate.sh` blocks `createConfluencePage`, `updateConfluencePage`, `slack_send_message`, and friends until the prose body has been marked via `.claude/hooks/humanize-mark.sh`. That gate runs orthogonally to this skill.

Use `impeccable` for visual/UI/design slop.

Use this skill for code, comments, doc structure, repo artifacts, PR text, ticket bodies, and Claude Code replies.

If multiple skills apply, run the specific skill first, then this skill as the final gate.

## Final rule

A clean output should feel like it came from a competent maintainer under time pressure: specific, boring where boring is good, and ruthless about anything that does not pay rent.
