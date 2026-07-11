# ai-routing

A **smart model router for Claude Code** — route each task to the cheapest/fastest model that clears the quality bar, across Claude tiers and external providers (OpenAI Codex/GPT-5.6, SpaceXAI Grok, Google Gemini), and log every decision for periodic self-improvement review.

Ships the `model-router` skill plus an interactive, peer-reviewed model-comparison report. Design goal: capability-tiered routing with a cheap default and explicit escalation, external-provider lanes for the jobs they win, and hard guardrails so quality- or safety-sensitive work never leaves the incumbent model.

## Contents

```
skills/model-router/SKILL.md   # /smart-route — tiered + multi-provider routing, guardrails, self-review
report/model-comparison.html   # interactive Claude/Codex/Grok/Gemini comparison (self-contained, offline)
```

## The routing ladder (July 2026)

Cheapest tier that clears the bar; escalate on complexity signals:

1. Bulk / classify / lookups → Gemini Flash-Lite / Claude Haiku 4.5
2. Well-specified coding w/ tests → Grok 4.5 / GPT-5.6 Luna (risk-tiered verify)
3. **Default agentic coding / review / planning → Claude Sonnet 5**
4. Hard multi-file / orchestration / merge-critical → Claude Opus 4.8
5. Ceiling cases (budget-gated) → Claude Fable 5
6. Long-context corpus, read path only → Gemini 3.1 Pro
7. Long terminal agents, sandboxed → GPT-5.6 Sol

**Guardrails:** style-locked content → keep on the incumbent model (org policy); high-stakes/regulated code (e.g. financial, security) → model-independent controls, never unsupervised on any model; risk-tiered verification for lower-trust models; sandbox every autonomous agent.

## The report

Open `report/model-comparison.html` in any browser — an interactive comparison of Claude / GPT-5.6 / Grok 4.5 / Gemini 3.1 Pro: a work-type router picker, validated pricing & benchmark charts, a sortable model table, token-efficiency notes, and guardrail callouts. It was critiqued by four frontier models (Gemini, Fable 5, Grok 4.5, GPT-5.6 Sol) and corrected accordingly; benchmark numbers are July-2026 and partly vendor-reported, so treat deltas as directional and re-verify pricing at model GA.

## Install

The router reads a **capability registry** (your models, access paths, and style-locked agents) that is intentionally *not* shipped here — provide your own alongside the skill. Then symlink/junction the skill into your Claude skills dir:

```bash
# macOS / Linux
ln -s "$(pwd)/skills/model-router" ~/.claude/skills/model-router
```
```powershell
# Windows (junction, no admin needed)
cmd /c mklink /J "$env:USERPROFILE\.claude\skills\model-router" "$(Resolve-Path .\skills\model-router)"
```

## License

MIT — see `LICENSE`.
