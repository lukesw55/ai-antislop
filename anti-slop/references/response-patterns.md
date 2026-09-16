# Assistant Response Patterns

Use this when the final assistant reply may influence repo work or when the user asks to remove AI tells.

## C1 — Restating the prompt

Slop:

```text
You asked me to review the repository and identify opportunities for improvement.
```

Fix: start with the finding or artifact.

## C2 — Tool narration

Slop:

```text
I will now inspect the files and then create the changes.
```

Fix: provide progress only when it helps the user steer work. Do not narrate obvious tool use in the final answer.

## C3 — Sycophantic openers

Slop:

```text
Great question! You're absolutely right to think about this.
```

Fix: answer directly.

## C4 — Trailing summaries

Slop:

```markdown
## Summary
In summary, these changes improve quality and maintainability.
```

Fix: end with the deliverable, decision, or next action.

## C5 — Follow-up spam

Slop:

```text
Let me know if you want me to also add tests, docs, examples, CI, and deployment.
```

Fix: offer at most one relevant follow-up when it is genuinely useful.

## C6 — Over-structured small answers

Slop: headings, bullets, and tables for a two-sentence answer.

Fix: use the simplest shape that preserves clarity.

## C7 — Unsupported confidence

Block:

- "This is fixed" when no verification ran
- "Tests pass" when tests were not run
- "No issues remain" when only a partial scan happened
- "Production ready" without evidence

Fix:

```text
I changed the parser and ran `pytest tests/parser`. I did not run the full suite.
```

## C8 — Useful progress updates

Progress updates are not slop when work is long-running and the user needs orientation.

Good update:

```text
I found the main issue: README claims MIT but the repo has no LICENSE. I am fixing that while keeping the package minimal.
```

Bad update:

```text
I am now opening the file. Next I will read it. Then I will edit it.
```

## C9 — Multilingual triggers

Respect the conversation language, but keep repo artifacts in the repo's established language unless the user asks otherwise.

Portuguese slop triggers include:

- `tira o ruído`
- `corta o boilerplate`
- `com cara de IA`
- `com cara de ChatGPT`
- `tá com slop`
- `menos genérico`
- `sem firula`

These triggers tell you when to apply the skill. The executable detectors in `rules/rules.json` match English phrasing only.

## C10 — Portable sentences

Slop:

```text
This change improves reliability and makes the system easier to maintain.
```

The sentence would fit any change in any repository. Fix: state the specific mechanism or consequence.

```text
Retries now stop after three attempts, so a dead upstream no longer holds a worker for 90 seconds.
```

## C11 — Unverifiable attribution

Slop:

```text
Experts agree this is the recommended approach, and studies show it is faster.
```

Fix: name the source or drop the claim. If no source exists, say so.

```text
The functools documentation recommends lru_cache for this case. I did not benchmark it.
```

## C12 — Synonym cycling

Slop:

```text
The scanner reads the file. The tool then parses the document. The utility finally reports on the artifact.
```

Fix: keep one name per object. Repetition for clarity is not slop.

```text
The scanner reads the file, parses it, and reports findings.
```

## C13 — Artificial kicker

Slop:

```text
In the end, code is a conversation with the future.
```

Fix: delete the closing aphorism and end on the last concrete result or next action. Do not replace it with a better metaphor.

## Preserve

Cleanup keeps the author's voice and the reader's ability to judge. Keep:

- vocabulary, cadence, humor, bluntness, and digressions that belong to the author
- useful uncertainty such as "I think", "not verified", or "only tested on Linux"
- one consistent term per object, even when it repeats
- operational detail, constraints, and examples required to act

Correct and preserve, side by side:

```text
Fix:      "This module handles all edge cases."
          -> "The parser rejects malformed headers and logs the offending line."
Preserve: "Honestly, I'm not sure the retry path is right; I only tested it against the mock."
          (uncertainty and voice)
Preserve: "Run step 4 before step 5 or the migration locks the table."
          (operational constraint)
```
