# 🧹 anti-slop

> Stop shipping AI tells. Ship the smallest useful change.

Claude Code skill that runs as a quality **gate** before any code, doc, PR text, or chat reply leaves the model. Strips defensive guards, single-use abstractions, banner sections, narration logs, and sycophantic filler — without touching substance.

![License](https://img.shields.io/badge/license-MIT-green)
![Skill](https://img.shields.io/badge/Claude%20Code-skill-blue)
![Patterns](https://img.shields.io/badge/slop%20patterns-44-purple)
![Modes](https://img.shields.io/badge/modes-3-orange)

---

## Why

LLMs default to verbose, defensive, template-shaped output. That output bloats diffs, slows reviews, and makes humans clean up after the model. `anti-slop` flips the default: lean output by construction, not by post-hoc editing.

```python
# Before — what Claude writes unprompted
def total(items: list[Order]) -> float:
    if items is None:
        return 0.0
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    return sum(o.amount for o in items if o is not None)

# After — what anti-slop ships
def total(items: list[Order]) -> float:
    return sum(o.amount for o in items)
```

Same behavior. Fewer lines. Trusts the type system. Six lines of defensive crud gone.

---

## Install

```bash
git clone git@github.com:lucasbpl/ai-antislop.git
cp -r ai-antislop/anti-slop ~/.claude/skills/
```

Restart Claude Code. Skill auto-loads via the `Skill` tool when triggers fire.

For runtime enforcement, wire the bundled Stop hook — it reads the final assistant message from the session transcript, scans it for slop patterns, and asks Claude to revise before stopping. For the personal install above:

```jsonc
// ~/.claude/settings.json
{
  "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "python3 \"$HOME/.claude/skills/anti-slop/hooks/anti-slop-stop.py\"", "timeout": 10 }] }]
  }
}
```

If you vendor the skill inside a project (`.claude/skills/anti-slop/`), use the `${CLAUDE_PROJECT_DIR}` variant from [`anti-slop/hooks/hooks.example.json`](anti-slop/hooks/hooks.example.json) instead.

Set `ANTI_SLOP_HOOK_BLOCK=1` to make the hook blocking instead of advisory. There is also a dependency-free static scanner for existing repos:

```bash
python3 anti-slop/scripts/scan_repo_slop.py path/to/repo --fail-on-block
```

---

## What it kills

44 patterns across five surfaces, organized under an S1–S4 slop taxonomy (formulaic, false, clickbait, workplace distraction).

| Surface | Patterns | Examples |
|---|---|---|
| **Code (A1–A10)** | 10 | boundary guards on internal callers, try/except without recovery, single-use wrappers, generic names (`data`, `Helper`, `Manager`), restating comments, narration logs, premature configurability, dead compat aliases, type inflation, banner regions |
| **Docs / markdown (B1–B10)** | 10 | template sections (Overview/Details/Conclusion), README that restates the repo name, label-colon bullets, forced symmetry, static metadata nobody maintains, decorative emoji, PR/commit slop, ADR slop, changelog slop, ticket slop |
| **Chat replies (C1–C9)** | 9 | restating the prompt, tool narration, sycophantic openers, trailing summaries, unsolicited follow-up offers, over-structured small answers, unsupported confidence, useless progress updates, multilingual triggers |
| **Repo contamination (D1–D8)** | 8 | unrequested artifacts, fake maturity signals, template docs, unused scaffolding, generated assets without provenance, unsupported repo claims, summary files that restate work, abstractions with no caller |
| **Multimodal (M1–M7)** | 7 | impossible visual claims, distorted AI media artifacts, clickbait media framing, missing provenance, prompt slop, transcript/audio slop, alt text slop |

Each pattern ships with concrete slop → fix examples in [`anti-slop/references/`](anti-slop/references/), loaded on demand so the base [`SKILL.md`](anti-slop/SKILL.md) stays lean.

---

## Three modes

| Mode | When | Output |
|---|---|---|
| **Gate** | creating new output | applied silently before final reply |
| **Sweep** | reviewing existing material | `Findings` + `Rewrites` diff + `Remaining smell` |
| **Diff** | reviewing PRs | one line per finding: `path:line — TAG issue. Suggested change: ...` |

---

## Triggers

Auto-fires when the user says (EN/PT):

- "remove AI slop" · "kill the slop" · "this looks AI-generated"
- "clean this up" · "less verbose" · "make it leaner"
- "tira o ruído" · "tá com cara de ChatGPT" · "essa resposta tá com cara de IA"
- "corta o boilerplate" · "esse código tá com slop" · "menos genérico" · "sem firula"

Also fires automatically before any non-trivial generation: code edits, new files, comments, docstrings, README sections, PR/commit/ticket text, ADRs, plans, or replies longer than two sentences.

Skips on raw logs, JSON, CSV, one-liners, and exact-spec mechanical edits.

---

## Non-negotiables

1. Preserve behavior, evidence, constraints, edge cases, security checks, citations, and operational detail.
2. Remove generic structure, unsupported claims, fake maturity signals, and decorative polish.
3. Do not create files, abstractions, wrappers, docs, metadata, or config without a permanent repo purpose.
4. Trust internal contracts unless code crosses a boundary: user input, public API, filesystem, network, auth, payment, migration, or security.
5. Replace vague praise and broad claims with repo-grounded facts, or mark them as assumptions.
6. Prefer a small useful change over a polished-looking artifact.
7. Anti-slop is not blind minimalism.

> If deletion removes load-bearing context, you removed too much.

---

## Layout

```text
ai-antislop/
├── LICENSE
└── anti-slop/
    ├── SKILL.md                 # frontmatter + gate rules + 3 modes
    ├── references/              # pattern catalogues, loaded on demand
    │   ├── slop-taxonomy.md     # S1–S4 classes + severity mapping
    │   ├── code-patterns.md     # A1–A10
    │   ├── docs-patterns.md     # B1–B10
    │   ├── response-patterns.md # C1–C9
    │   ├── repo-contamination.md# D1–D8
    │   └── multimodal-patterns.md # M1–M7
    ├── hooks/                   # optional Stop hook + example config
    ├── scripts/                 # scan_repo_slop.py static scanner
    └── evals/                   # test prompts + trigger queries
```

Mirrors [anthropics/skills](https://github.com/anthropics/skills): one folder per skill, each with a `SKILL.md` carrying YAML frontmatter (`name`, `description`). Drop into `~/.claude/skills/` and Claude picks it up.

---

## License

MIT.
