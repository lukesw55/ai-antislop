# 🧹 anti-slop

> Stop shipping AI tells. Ship the smallest useful change.

Claude Code skill that runs as a quality **gate** before any code, doc, PR text, or chat reply leaves the model. Strips defensive guards, single-use abstractions, banner sections, narration logs, and sycophantic filler — without touching substance.

![License](https://img.shields.io/badge/license-MIT-green)
![Skill](https://img.shields.io/badge/Claude%20Code-skill-blue)
![Patterns](https://img.shields.io/badge/slop%20patterns-22-purple)
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

For repo-wide enforcement, wire it into a `UserPromptSubmit` hook so every prompt activates the gate:

```jsonc
// ~/.claude/settings.json
{
  "hooks": {
    "UserPromptSubmit": [{ "command": "echo 'ANTI-SLOP GATE ACTIVE. Run anti-slop in Gate mode before output.'" }]
  }
}
```

---

## What it kills

22 patterns across three surfaces.

| Surface | Patterns | Examples |
|---|---|---|
| **Code (A1–A10)** | 10 | boundary guards on internal callers, try/except without recovery, single-use wrappers, generic names (`data`, `Helper`, `Manager`), restating comments, narration logs, premature configurability, dead compat aliases, type inflation, banner regions |
| **Docs / markdown (B1–B6)** | 6 | template sections (Overview/Details/Conclusion), README that restates the repo name, label-colon bullets, forced symmetry, static metadata nobody maintains, decorative emoji |
| **Chat replies (C1–C6)** | 6 | restating the prompt, tool narration, sycophantic openers, trailing summaries, unsolicited follow-up offers, over-structured small answers |

Each pattern in [`anti-slop/SKILL.md`](anti-slop/SKILL.md) ships with concrete slop → fix examples in real code.

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
- "corta o boilerplate" · "esse código tá com slop"

Also fires automatically before any non-trivial generation: code edits, new files, comments, docstrings, README sections, PR/commit/ticket text, ADRs, plans, or replies longer than two sentences.

Skips on raw logs, JSON, CSV, one-liners, and exact-spec mechanical edits.

---

## Non-negotiables

1. Ship the smallest useful change.
2. Trust internal contracts unless a boundary is involved.
3. Delete generic structure instead of polishing it.
4. Do not create files the user did not ask for.
5. Do not narrate obvious tool use.
6. Do not add abstractions for hypothetical reuse.
7. Preserve substance while removing slop.

> If removing "AI slop" removes evidence, behavior, constraints, or useful context, you removed too much.

---

## Layout

```
ai-antislop/
└── anti-slop/
    └── SKILL.md     # frontmatter + 22 patterns + 3 modes
```

Mirrors [anthropics/skills](https://github.com/anthropics/skills): one folder per skill, each with a `SKILL.md` carrying YAML frontmatter (`name`, `description`). Drop into `~/.claude/skills/` and Claude picks it up.

---

## License

MIT.
