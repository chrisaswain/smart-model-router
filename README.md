# smart-model-router

A **smart model router for Claude Code** — route each task to the cheapest/fastest model that clears the quality bar, across Claude tiers and external providers (OpenAI Codex/GPT-5.6, SpaceXAI Grok, Google Gemini), and log every decision for periodic self-improvement review.

Ships the `model-router` skill plus a reference routing table. Design goal: capability-tiered routing with a cheap default and explicit escalation, external-provider lanes for the jobs they win, and hard guardrails so quality- or safety-sensitive work never leaves the incumbent model.

## Contents

```
skills/model-router/SKILL.md      # /smart-route — operating modes + tiered/multi-provider routing, guardrails
skills/model-router/routing-table.json  # de-identified measured baseline the operating modes select over
hooks/routing_gate.py             # UserPromptSubmit hook: injects the routing pick automatically
install.py                        # links the skill, registers the hook, verifies
```

## Operating modes

Pick one objective; **Balanced is the default**:

- **Frugal** — cheapest model that clears the quality bar.
- **Fast** — lowest measured latency that clears the bar.
- **Balanced** — cheapest within a tolerance of the best (CI-aware); the sensible default.
- **Deep** — the capability ceiling.

Modes select over a **measured routing table** (`routing-table.json`), produced by a companion benchmark called route-proof (not yet public). This repo ships a **de-identified reference baseline** (real metrics from one run, identity removed) so the modes work out of the box. Read the next section before you rely on the numbers. The guardrail layer always runs first, thin/unmeasured data falls back to the heuristic ladder, and a **measured tie is surfaced to you to choose** rather than broken arbitrarily. Full rules in `skills/model-router/SKILL.md` → **Operating Modes**.

## The routing ladder (fallback)

Cheapest tier that clears the bar; escalate on complexity signals:

1. Bulk / classify / lookups → a current Gemini Flash-Lite tier (pins retire often, confirm yours is live) / Claude Haiku 4.5
2. Well-specified coding w/ tests → Grok 4.5 / GPT-5.6 Luna (risk-tiered verify)
3. **Default agentic coding / review / planning → Claude Sonnet 5**
4. Hard multi-file / orchestration / merge-critical → Claude Opus 4.8
5. Ceiling cases (budget-gated) → Claude Fable 5
6. Long-context corpus, read path only → Gemini 3.1 Pro
7. Long terminal agents, sandboxed → GPT-5.6 Sol

**Guardrails:** style-locked content → keep on the incumbent model (org policy); high-stakes/regulated code (e.g. financial, security) → model-independent controls, never unsupervised on any model; risk-tiered verification for lower-trust models; sandbox every autonomous agent.

## What the table is, and what it is not

The shipped table is a **reference baseline, not a benchmark of these models**. Read `meta` in `routing-table.json`; it carries the full disclosure and travels with the file. The short version:

- **It is one person's measurements, and only partly from real code.** Only the `coding` cells come from a private codebase: 5 commits harvested from its git history, graded by whether that codebase's own tests pass. Every other work-type ran 2 or 3 tasks from the benchmark's shipped default set, each with its own scorer (code-review by planted-defect recall, style-writing by an LLM judge, and so on), not by any test suite. Absolute pass rates and costs transfer weakly. The selection semantics and the cell schema are the transferable part.
- **The samples are small.** n per cell is 2 to 5 tasks. The confidence intervals are wide because the underlying uncertainty is real.
- **Most work types do not auto-route.** Only `coding` and `long-context` currently have any cell clearing the confidence floor (pass@k >= 0.5, n >= 3, CI width <= 0.6 x validity). The other five always fall back to the heuristic ladder above. This is by design: the floor is what stops thin data from driving decisions.
- **An absent model was usually not measured, not beaten.** `meta.excluded` names every gap and why. Notably the GPT/Codex family has no `coding` cells because a harness defect truncated their prompts, not because they failed.
- **A listed model is not proof it is callable from your environment.** Pins get retired upstream. Probe before you route.
- **`cost_per_solved_usd` of 0.0 means subscription-covered, not free.** `null` means not captured.

## Status

Provided as-is under MIT. This is a working artifact from one person's routing setup, published so others can start from something real rather than a blank table.

The table refreshes only when its owner reruns the benchmark and promotes the result; `meta.date` is the version stamp. There is no release schedule, no compatibility promise, and no support commitment. Issues are welcome, answered when time allows.

## Install

```bash
git clone https://github.com/chrisaswain/smart-model-router
cd smart-model-router
python install.py
```

Then restart Claude Code. Or just point Claude at this repo and ask it to run `install.py`.

That links the skill and registers the routing hook, which is what makes routing happen automatically as you work rather than only when you ask. Full details, verification, uninstall, and the one setting worth editing are in [INSTALL.md](INSTALL.md).

## License

MIT — see `LICENSE`.
