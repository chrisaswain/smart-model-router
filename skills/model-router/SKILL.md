# Smart Model Router

Route tasks to the cheapest/fastest model that can handle them well — across Claude tiers **and** external providers (OpenAI Codex/GPT-5.6, SpaceXAI Grok, Google Gemini). **Claude Sonnet 5 is the default working tier**; the current session (Opus) classifies work, delegates simpler tasks down (Haiku), escalates hard tasks up (Opus 4.8 → Fable 5), and dispatches specific jobs to external providers via the Multi-Provider Lane. Every routing decision is logged for periodic self-improvement review.

> **Model roster (2026-07):** Claude Fable 5 / Opus 4.8 / Sonnet 5 / Haiku 4.5 · GPT-5.6 Sol/Terra/Luna · Grok 4.5 · Gemini 3.1 Pro / 3 Flash / Flash-Lite. Rebalanced 2026-07-11 after a four-model peer review. Not every tier will be callable from your machine; ignore any provider you have not installed.

## Invocation

- **Automatic:** This skill's routing logic applies passively during normal work. When Opus detects a delegatable task, it suggests or auto-delegates based on complexity.
- **Direct:** `/smart-route <prompt>` — explicitly route a task through the model selector
- **Review:** `/smart-route review` — analyze the performance log and produce improvement recommendations
- **Stats:** `/smart-route stats` — show routing statistics summary
- **Mode:** `/smart-route --mode frugal|fast|balanced|deep <task>` — set the operating mode (default **Balanced**). Plain language works too ("use fast mode"). See **Operating Modes** below.

## Operating Modes

The router runs in one of four **operating modes** — an objective for *how* to choose among capable models for a task's work-type. Set per session/task; **Balanced is the default**. Modes select over a measured routing table (`routing-table.json` in this skill's directory — this repo ships a **de-identified reference baseline**; see its `meta` block for coverage, exclusions and sample sizes before relying on it). The tiers/ladder below are the fallback when the table is thin.

| Mode | Optimizes | Rule over the measured table | internal |
|---|---|---|---|
| **Frugal** | lowest $ cost | cheapest model whose pass@k clears the work-type quality bar | `thrift` |
| **Fast** | lowest latency | lowest measured **median** wall-time clearing the bar | `fast` |
| **Balanced** (default) | quality-per-cost | cheapest model within δ of the best whose **CI-low** clears the bar | `balanced` |
| **Deep** | capability ceiling | highest measured pass@k (see saturation note) | `max` |

### Order of operations (every route)

1. **Guardrail layer FIRST — overrides everything.** Before any measured data: style-locked / brand-voice → incumbent model (org policy); autonomous agent → sandboxed. A guardrail wins regardless of mode or table. Trading / execution / regulated code is routed normally by capability/cost (not pinned to a provider by default); the separate **execution-safety floor** (no unsupervised live-order authority) always holds regardless of author.
2. **Consult the measured table** for the task's work-type under the active mode's rule.
3. **Resolve:**
   - **Single clear winner** (clears the confidence floor) → route; attribute with the mode + evidence.
   - **Measured tie** — 2+ candidates the mode can't separate (Deep: equal pass@k, overlapping CIs; Frugal/Balanced: equal cost, e.g. several subscription-free models; Fast: near-equal median latency) → **never pick arbitrarily.** Present the tied candidates to the user and route to their choice; record it in your preference store so you don't re-ask.
   - **Below the confidence floor / no cell** (too few tasks, wide CI, low-validity judge) → **fall back to the heuristic ladder** below.

### Thresholds & tie detection

Compute candidates/ties from the table cells with these values (they match route-proof's engine). `routing-table.pr.md`, if present, is a human-readable evidence snapshot (non-runtime).

- **Quality bar** (pass@k): **0.5**.
- **Balanced band** δ: **0.10** (within 0.10 pass@k of the best AND CI-low ≥ 0.5).
- **Confidence floor:** a cell auto-routes only if N ≥ **3** tasks AND Wilson CI width ≤ **0.6 × validity**; below → heuristic ladder.
- **Tie margins:** Frugal/Balanced = candidates at the same minimum cost; Fast = within **15%** of the fastest median latency; Deep = top pass@k AND tightest CI-low (best-evidenced ceiling). If a tie set exceeds 4, present the most distinct 3-4 (fastest / mid / premium) plus "other".

### Deep mode + measured saturation

When tasks saturate (the top models tie at ~100% with overlapping CIs — as coding does in the shipped baseline), `max` can't separate them; that's a tie → Deep prompts rather than guessing, or escalates via the ladder if you decline. Deep's measured ceiling isn't established for saturated work-types until a harder-task run exists.

## Task Classification

Classify every delegatable task into one of three tiers:

### Tier 1 — Haiku 4.5 (simple, pattern-matching, retrieval)

Cost: ~$1/M input, ~$5/M output — **5x cheaper than Opus 4.8 output** *(corrected 2026-07-11; the old $0.25/$1.25 was stale Haiku-3 pricing)*

| Task Pattern | Examples |
|---|---|
| File content retrieval | "What's in config.json?", "Show me the imports in app.tsx" |
| Simple grep/find | "Find all files that import X", "Where is Y defined?" |
| Basic formatting/transformation | "Convert this list to a markdown table", "Reformat this JSON" |
| Simple enumeration | "List all routes in this app", "What env vars does this use?" |
| Straightforward Q&A (lookup) | "What version of React is this using?", "What's the default port?" |
| Status checks | "Is there a lock file?", "What branch am I on?" |
| Simple text transforms | "Convert camelCase to snake_case in these names", "Sort these alphabetically" |
| Template generation | "Generate a basic .gitignore for Python", "Scaffold a test file" |

### Tier 2 — Sonnet 5 (the DEFAULT working tier — moderate-to-strong reasoning)

Cost: ~$3/M input, ~$15/M output (intro $2/$10 through Aug 31, 2026) — **~1.7x cheaper than Opus 4.8 output**

**Rebalanced 2026-07-11 (post 4-model peer review):** Sonnet 5 is now the **default** for coding, PR review, and planning — not just Tier-2 delegation. It clears most agentic coding work (~82% SWE-Verified); reserve Opus 4.8 for merge-critical / hard multi-file / orchestration, and Fable 5 for budget-gated ceiling cases. "Opus by default" is cost-uncalibrated.

| Task Pattern | Examples |
|---|---|
| Document summarization | "Summarize this README", "Give me the key points from this file" |
| Test case writing | "Write unit tests for this function", "Add test coverage for this module" |
| PR/commit message drafting | "Draft a PR description for these changes" |
| Multi-file exploration | "How does the auth flow work across these files?" |
| Moderate refactoring | "Rename this variable across the file", "Extract this into a helper" |
| Documentation generation | "Generate JSDoc for these functions", "Write API docs for this endpoint" |
| Data analysis (simple) | "Parse this CSV and show top 10 by revenue" |
| Translation/localization | "Translate these UI strings to Spanish" |
| Boilerplate code generation | "Create a CRUD API for this model", "Scaffold a React component" |
| Dependency analysis | "What does this package do? Should we keep it?" |

### Tier 3 — Opus 4.8 / Fable 5 (escalation tier — hardest work)

*Escalate here from the Sonnet-5 default when a task hits these patterns. Opus 4.8 for hard multi-file / orchestration / merge-critical / security; **Fable 5** for budget-gated ceiling cases only. Not a "stay put" tier — it's where the default escalates TO.*

| Task Pattern | Why Opus |
|---|---|
| Architectural decisions | Requires judgment, tradeoff analysis, full project context |
| Complex debugging | Multi-step reasoning, hypothesis testing |
| Multi-file refactoring with design decisions | Needs to understand intent, not just pattern-match |
| Nuanced writing with specific voice/tone | Claude Opus produces distinctly better prose |
| Code review with judgment calls | Ambiguity handling, risk assessment |
| Agentic multi-step workflows | Orchestration, tool chaining, error recovery |
| Tasks requiring full conversation context | Agent doesn't get prior conversation history |
| Security-sensitive analysis | Needs careful, thorough reasoning |
| Anything the user is actively collaborating on | Context continuity matters |

## Multi-Provider Lane (external CLIs + Gemini) — added 2026-07-11

Beyond the Claude tiers, three external providers can be routed for specific jobs if you have their CLIs installed and authenticated. **Log each with a `provider` field.**

### The rebalanced default ladder

**This ladder is the FALLBACK** — used when the measured table has no confident cell for the (work-type, mode) (below the confidence floor, or unmeasured). When the table has a confident cell, the active operating mode's selection over it takes precedence (see **Operating Modes**).

1. **Classify / extract / bulk** → a current Gemini Flash-Lite tier or Haiku 4.5 (Flash-Lite pins retire often; confirm yours is live, see `meta.invocability_warning`)
2. **Well-specified coding w/ tests** → Grok 4.5 (`grok.exe`) or GPT-5.6 Luna (`codex exec -m gpt-5.6-luna`)
3. **Default agentic coding / review / planning** → **Claude Sonnet 5**
4. **Hard multi-file / orchestration / merge-critical** → Claude Opus 4.8
5. **Known ceiling cases** (budget-gated) → Claude Fable 5 (Agent `model: fable`)
6. **Long-context corpus, READ path only** → Gemini 3.1 Pro (API/console; MCP exposes only 2.5)
7. **Long terminal agents, sandboxed** → GPT-5.6 Sol (`codex exec -m gpt-5.6-sol`)

### 🟢 Measure it on your own code (personalized benchmark)

Vendor "best coder" rankings can invert on *your* actual code. A companion approach — mine your own private repo into coding tasks (a commit that changed source+tests becomes a task: revert to the parent, hand the model the failing tests as the spec, grade by whether they pass in an isolated worktree) — lets you measure which model actually solves your kind of work, and at what cost.

A **full-matrix reference run** (5 coding task types + answer-path work-types × the model roster) is shipped here as `routing-table.json` (de-identified real metrics — the operating modes select over it). Headline findings:

- **Coding capability saturates** — four Claude tiers and Grok 4.5 all solve 100% — so route by cost/speed. **Fast → Grok 4.5** (~2.5 min/task; the next fastest of the saturated set is 2.6x slower).
- **Cost cannot rank the whole saturated set.** Among the models that solve 100%, only three have a captured cost (Sonnet 5 cheapest, then Opus 4.8, then Fable 5); Haiku 4.5 and Grok 4.5 have no cost captured for their coding cells (see `meta.cost_basis`; null means not captured, and the reason is not recorded). Absent cost is not zero cost, so treat a Frugal pick between those two as unranked and choose deliberately.
- **Gemini fails agentic coding** in patch-gen mode (can't do multi-file features) but **scores well on answer-path** (extraction / grounded-QA) — route it to Q&A, not large agentic coding. Treat this as directional: neither extraction nor grounded-QA has a single cell above the confidence floor, and the reasoning cells carry validity 0.3 and are not evidence of anything.
- **coding + long-context auto-route; the other five work-types fall to the heuristic ladder** (below the confidence floor). See `meta.coverage` in `routing-table.json` for the per-work-type counts.

**Lesson:** don't reach for the premium model when a cheap/fast one measurably ties it *on your work*. Caveat: saturated task classes measure competence + cost, not the capability ceiling — harder tasks discriminate (Deep prompts on ties until then). These findings describe one private codebase; measure your own before trusting them.

### How to invoke externally

- **Grok:** `~/.grok/bin/grok.exe -p "<self-contained prompt>" --model grok-4.5 --output-format json` → parse `.text`.
- **Codex/GPT-5.6:** pipe prompt via **stdin** (`Get-Content prompt | codex exec -m <model> -s read-only --skip-git-repo-check -o out.txt`); passing the prompt as an arg while stdin is open can hang.
- **Gemini:** `mcp__gemini__generate_text` (MCP is 2.5-family today) or research MCPs.

### Media & voice (Gemini TTS)

For narration / text-to-speech, route to **Gemini TTS** via a `gemini-media` MCP server (`generate_audio`):
- Model **`gemini-2.5-flash-preview-tts`**; default voice **`Charon`** (30 prebuilt voices; params `voiceName`, `languageCode`, `prompt`).
- Output is raw PCM (s16le, 24kHz, mono) → convert with `ffmpeg -f s16le -ar 24000 -ac 1 -i voice.pcm voice.wav`.
- **Steer delivery with prose + punctuation, not bracket tags** — `[pause]`/`[emphasis]`-style tags are inert on this model (unlike ElevenLabs, where they're honored). This is the default TTS lane; fall back to local/system TTS only if Gemini is unavailable.

### Guardrails (non-negotiable)

**This is the guardrail layer — it runs FIRST on every route (step 1 of Operating Modes) and overrides any measured/mode selection.**

- **Style-locked content** (specialized agents with a locked voice, methodology, or brand — domain-expert advisors, brand-voice writers, calibrated analysts) → **keep on the incumbent model, org policy.** Never route out. (Configure the match list in `hooks/routing_gate.py` → `STYLE_LOCKED`.)
- **Trading / execution code** — **authorship is not provider-restricted by default:** any model may write trading code (routed by the normal mode/table logic), on the principle that an independent adversarial review + verification contracts catch defects regardless of author. Orgs with IP-retention constraints may optionally pin it to the incumbent. **The execution-safety floor is always retained and non-negotiable:** model-independent controls (deterministic tests, look-ahead-bias checks, paper-trading, human approval), and no model gets unsupervised live-order authority.
- **Grok output → risk-tiered verify:** route money/security/prod paths through a Claude gate; trust tests for throwaway scripts. Blanket "always verify" pays two models and erases the cost win.
- **Sandbox EVERY autonomous agent** (Sol, Grok, Claude) — no unsupervised network + secrets. METR flagged Sol for in-scaffold reward-hacking → keep Sol off gating CI specifically.
- **Availability check:** GPT-5.6 Sol may be partner-preview; confirm access before routing to it. Gemini 3.1 Pro needs API/console (not the current MCP).

## Delegation Protocol

### When to auto-delegate (no suggestion needed)

Auto-delegate to a subagent when ALL of these are true:
1. The task clearly falls into Tier 1 or Tier 2
2. The task is self-contained (doesn't need prior conversation context)
3. The task output can be verified at a glance
4. The user hasn't indicated they want Opus-level attention on this

### When to suggest delegation

Suggest delegation when:
- The task is borderline Tier 2/3
- The task is large but could be parallelized across cheaper agents
- The user is doing bulk work where cost matters

Suggestion format:
```
> This looks like a Tier {1|2} task — I can delegate to {Haiku|Sonnet} to save tokens. Want me to route it?
```

### When to NEVER delegate

- The user explicitly said `/smart-route opus` or similar
- The task involves secrets, credentials, or security review
- The task is part of an active back-and-forth dialogue
- The output will be shown directly to someone else (PR comments, messages, etc.)
- The user previously escalated a similar task from a cheaper model

## Execution Steps

### Step 1: Classify

Determine the tier using the tables above. When uncertain, default UP (Sonnet over Haiku, Opus over Sonnet).

### Step 2: Delegate

Spawn an Agent with the appropriate model:

```
Agent({
  description: "<short task description>",
  model: "haiku",  // or "sonnet"
  prompt: "<self-contained task prompt with all needed context>"
})
```

**Critical:** The agent has NO conversation history. The prompt must be fully self-contained:
- Include file paths to read
- Include the specific question or task
- Include expected output format
- Include any constraints or preferences

### Step 3: Quality gate

When the agent returns, do a quick quality check before presenting to the user:
- Does the output actually answer the question?
- Is the output format correct?
- Are there obvious errors or hallucinations?
- For code: does it look syntactically correct?

If quality is insufficient:
1. Log an escalation event
2. Either fix it yourself (Opus) or re-delegate to the next tier up
3. Note the task pattern for future routing adjustments

### Step 4: Present with attribution

**MANDATORY — always show which model handled the work:**

```markdown
> **[Claude {Model}]** — {brief reason for model choice}

{output}
```

Examples:
```markdown
> **[Claude Haiku]** — simple file lookup

The config uses port 3000 with...
```

```markdown
> **[Claude Sonnet]** — test generation

Here are the unit tests for `calculateTotal()`...
```

If escalation happened:
```markdown
> **[Claude Sonnet → Opus]** — escalated: output needed refinement

{improved output}
```

### Step 5: Log the decision

Append a JSON line to the routing log (see Performance Tracking below).

## Performance Tracking

### Log Location

`logs/routing-log.jsonl`

### Log Format

Each routing decision appends one JSON line:

```json
{
  "ts": "2026-05-24T11:30:00Z",
  "task_type": "file_lookup|summarization|test_writing|exploration|...",
  "work_type": "coding|reasoning|extraction|grounded-qa|code-review|long-context|style-writing",
  "route_mode": "frugal|fast|balanced|deep",
  "route_source": "table|tie-prompt|heuristic-ladder|guardrail",
  "task_summary": "Find all React imports in src/",
  "model_selected": "haiku",
  "model_escalated_to": null,
  "escalation_reason": null,
  "outcome": "success|escalated|failed",
  "user_feedback": null,
  "tokens_estimated": 1500,
  "notes": ""
}
```

### Logging Rules

- Log EVERY routed task (not Opus-stays tasks — those are the default)
- If the user corrects or rejects output, update `user_feedback` to `"rejected"` and note why
- If the user accepts without comment, `user_feedback` stays `null` (implicit success)
- If the user says "nice" / "perfect" / "good", set `user_feedback` to `"positive"`
- If escalation occurs, record both `model_selected` and `model_escalated_to`

### Writing the Log

Use a Bash append to write each log entry:

```bash
echo '{"ts":"...","task_type":"...","model_selected":"...","outcome":"..."}' >> logs/routing-log.jsonl
```

### Auto-Review Trigger

After every log write, count the total entries:

```bash
wc -l < logs/routing-log.jsonl
```

**Auto-trigger a review when the count hits a milestone:**

| Entry Count | Action |
|---|---|
| 25 | Run a **mini-review** — just escalation rates and any obvious problems. One paragraph, inline. |
| 50 | Run **full review** (same as `/smart-route review`). Present findings + recommendations. |
| 100, 200, 500, ... | Run **full review** at every doubling/milestone after 50. |

The review runs inline — no user action needed. Present findings and ask for approval before applying any routing rule changes.

If the last review was within 25 entries of the current count (e.g., manual `/smart-route review` was just run), skip the auto-trigger to avoid redundancy.

Track the last auto-review count in the log itself:
```json
{"ts":"...","task_type":"meta_auto_review","model_selected":"opus","outcome":"success","notes":"auto-review at 50 entries"}
```

## Self-Improvement Review (`/smart-route review`)

When invoked, read the full routing log and produce an analysis:

### Step 1: Load data

```bash
cat logs/routing-log.jsonl
```

### Step 2: Compute metrics

| Metric | Formula |
|---|---|
| **Total routed** | Count of all log entries |
| **Haiku usage** | Count where model_selected = haiku |
| **Sonnet usage** | Count where model_selected = sonnet |
| **Escalation rate (Haiku)** | Escalated from haiku / Total haiku |
| **Escalation rate (Sonnet)** | Escalated from sonnet / Total sonnet |
| **User rejection rate** | user_feedback = rejected / Total |
| **Estimated token savings** | Sum of (opus_cost - actual_cost) for all delegated tasks |
| **Top escalation patterns** | Group escalated tasks by task_type, find recurring patterns |

### Step 3: Produce recommendations

Based on the data, recommend routing rule changes:

- **High escalation rate for a task type (>25%):** "Move `{task_type}` from Tier {N} to Tier {N+1}"
- **Zero escalations for a task type (50+ samples):** "Task `{task_type}` is well-placed at Tier {N}"
- **User rejections concentrated on a model:** "Increase quality threshold for `{model}` delegation"
- **Task types never delegated that could be:** "Consider delegating `{task_type}` — appears simple enough for Tier {N}"

### Step 4: Apply recommendations

If recommendations involve routing rule changes:

1. Present the findings to the user
2. If approved, update this SKILL.md with the adjusted task-type classifications
3. Log the rule change in the routing log with `task_type: "meta_rule_change"`

### Step 5: Output format

```markdown
## Model Router Performance Review

**Period:** {earliest_ts} to {latest_ts}
**Total tasks routed:** {N}

### Routing Distribution
- Haiku: {N} ({%})
- Sonnet: {N} ({%})
- Stayed on Opus: (not tracked — default path)

### Escalation Rates
- Haiku → Sonnet/Opus: {N}/{total_haiku} ({%})
- Sonnet → Opus: {N}/{total_sonnet} ({%})

### Top Escalation Patterns
1. {task_type}: {count} escalations — **Recommendation:** {move up / investigate / OK}
2. ...

### Estimated Token Savings
- Delegated {N} tasks that would have cost ~{X} on Opus
- Actual cost on cheaper models: ~{Y}
- **Net savings: ~{Z} tokens ({%} reduction)**

### Recommendations
1. {recommendation}
2. {recommendation}
```

## Stats Summary (`/smart-route stats`)

Quick one-liner stats from the log:

```markdown
**Model Router:** {N} tasks routed | Haiku: {N} | Sonnet: {N} | Escalations: {N} ({%}) | Est. savings: ~{N} tokens
```

## Parallel Delegation

For tasks that can be broken into independent subtasks, spawn multiple agents in parallel:

```
Example: "Summarize these 5 files"
→ Spawn 5 Haiku agents in parallel, one per file
→ Collect results and present together
```

This is where the biggest speed + cost wins happen. Look for opportunities to parallelize:
- Multi-file operations
- Batch lookups
- Independent subtasks within a larger request

## Experimentation Decision Points

When `global_experiment_mode` is enabled in `logs/ai-router/preferences.json`:

### Tier classification prompt

When auto-delegating, show the decision:

```markdown
> [Model Router — Decision Point]
> Task: "{task_summary}"
> Classification: Tier {N} ({model})
> A (Recommended): Claude {model} ({reasoning}, {cost_savings})
> B: Claude {alternative} ({tradeoff})
> C: Claude Opus (stay, best quality, highest cost)
> D: Compare {model} vs. Opus
```

### Quality check after delegation

After the delegated agent returns output, prompt:
```
> Quality check: Does this meet expectations? (yes / no / compare / lock)
```

- **yes** — log as successful delegation
- **no** — regenerate with Opus, log as failed experiment
- **compare** — generate with Opus side-by-side, user picks winner
- **lock** — save this tier as permanent preference for this task type

### Experiment logging

Log all experiments to `logs/ai-router/experiments.jsonl` with `router: "smart-route"`.

When experimentation is OFF (default), auto-delegation works as before — no decision prompts. The existing auto-delegate behavior (classify + delegate silently) remains the default to preserve speed.

## Edge Cases

- **Agent fails entirely** (crash, timeout): Fall back to Opus, log as `outcome: "failed"`
- **Ambiguous tier**: Default UP. It's better to overspend slightly than deliver poor quality.
- **User says "use Opus for everything"**: Respect it. Save as a feedback memory and stop delegating for the session.
- **Very short tasks** (< 3 tool calls expected): Do it yourself on Opus. Agent overhead isn't worth it.
- **Tasks requiring file writes/edits**: Always Sonnet minimum. Haiku should only read, never write.
