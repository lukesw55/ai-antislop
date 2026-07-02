# Multimodal Repo Slop Patterns

Use this when reviewing image, video, audio, screenshot, prompt, caption, alt text, transcript, or asset metadata that may enter the repo.

The skill does not need to inspect pixels or audio unless tools are available. It must still prevent slop in surrounding text, prompts, captions, metadata, and claims.

## M1 — Impossible or unverified visual claims

Block captions or docs that claim the asset proves something not verified.

Slop:

```markdown
This screenshot proves the checkout flow works on all mobile devices.
```

Fix:

```markdown
Screenshot of the checkout form at 390px width. Does not verify payment submission.
```

## M2 — Distorted AI media artifacts

Flag descriptions of generated images that mention or hide:

- impossible geometry
- missing limbs or extra fingers
- distorted text
- impossible reflections
- inconsistent shadows
- fake UI states

Fix: replace the asset, disclose generation, or avoid using it as evidence.

## M3 — Clickbait media framing

Trim captions or prompts optimized for attention rather than purpose.

Slop:

```text
Emotional rescue scene, shocking, viral, heartwarming, unbelievable transformation.
```

Fix: describe the actual repo use case.

## M4 — Missing provenance

Flag generated or synthetic assets without:

- source
- generation tool/model when relevant
- date or version when operationally important
- license/usage rights
- reason the asset belongs in the repo

Severity: `BLOCK` if the asset is public-facing or used as evidence.

## M5 — Prompt slop

Trim prompts that are generic, over-decorated, or contradictory.

Slop:

```text
Make it beautiful, professional, sleek, modern, stunning, viral, cinematic, high quality.
```

Fix:

```text
Generate a 16:9 dashboard screenshot mockup showing the failed-payment alert state. Use neutral UI styling and legible labels.
```

## M6 — Transcript and audio slop

Block:

- transcripts presented as exact when they are summaries
- fabricated speaker names
- cleanup that changes meaning
- music/audio descriptions that claim emotional impact as fact

Fix: label summary vs transcript, preserve uncertainty, and keep source metadata.

## M7 — Alt text slop

Alt text should serve accessibility, not SEO or marketing.

Slop:

```text
Amazing world-class dashboard revolutionizing payments.
```

Fix:

```text
Dashboard showing failed payments grouped by customer and retry status.
```
