# ai-antislop

Claude Code skill to detect and remove AI slop from generated outputs before they reach the repo or the user.

## Skills

- [anti-slop](anti-slop/SKILL.md) — gate that runs before code, docs, markdown, PR/commit/ticket text, plans, or replies longer than two sentences. Cuts boundary guards on internal callers, single-use abstractions, generic names, restating comments, narration logs, banner sections, label-colon bullets, sycophantic openers, trailing summaries, and other AI tells. Preserves substance.

## Install

Drop the skill folder into your Claude Code skills directory:

```bash
git clone git@github.com:lucasbpl/ai-antislop.git
cp -r ai-antislop/anti-slop ~/.claude/skills/
```

Claude Code picks it up on next session.

## Invoke

Triggers automatically on phrases like "remove AI slop", "kill the slop", "less verbose", "this looks AI-generated", "tira o ruído", "tá com cara de IA". See [anti-slop/SKILL.md](anti-slop/SKILL.md) for the full trigger list and operating modes.

## Layout

```
ai-antislop/
└── anti-slop/
    └── SKILL.md
```

Mirrors the structure used in [anthropics/skills](https://github.com/anthropics/skills): one folder per skill, each containing a `SKILL.md` with YAML frontmatter (`name`, `description`).
