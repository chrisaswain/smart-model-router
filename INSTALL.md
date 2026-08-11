# Install

Two pieces get installed:

- **the skill**, linked into `~/.claude/skills/model-router`, so you can ask for a routing recommendation on demand
- **the hook**, registered as a `UserPromptSubmit` hook, so routing suggestions are injected automatically as you work

The hook is the part that makes routing passive. Without it the skill still works, you just have to ask.

## Point Claude at it

Paste this to Claude Code:

> Clone https://github.com/chrisaswain/smart-model-router and run its install.py, then show me the output.

Or do it yourself:

```bash
git clone https://github.com/chrisaswain/smart-model-router
cd smart-model-router
python install.py
```

**Restart Claude Code afterwards.** The hook is read at startup.

Requires Python 3.9+ and Claude Code. No other dependencies, the hook is stdlib only.

## What install.py does

1. Links `skills/model-router` into `~/.claude/skills/` (junction on Windows, symlink elsewhere, copy if both fail).
2. Adds one `UserPromptSubmit` entry to `~/.claude/settings.json` pointing at `hooks/routing_gate.py`.
3. Runs the hook once against a sample coding prompt and prints what it injected, so you can see it working before you trust it.

It backs up `settings.json` first, appends rather than overwrites, and is idempotent. Existing hooks and unrelated settings are left alone. Keep the cloned directory where it is; the settings entry points at it by absolute path.

To remove everything: `python install.py --uninstall`

## Verify

Ask Claude anything code-shaped, for example "refactor this module and make the tests pass". You should see a `ROUTING GATE` line in the context. If you see nothing, the hook is not firing: confirm you restarted Claude Code, and run `python hooks/routing_gate.py` with `{"prompt":"refactor the auth module"}` on stdin to check it produces JSON.

## Configure

**`STYLE_LOCKED` in `hooks/routing_gate.py`** is the one thing worth editing. It lists domains that must never be routed away from your incumbent model regardless of what the table says, for example brand voice, legal, regulated, or clinical work. The shipped list is a generic starting set. Add your own agents, brands, and regulated areas. Set it to `None` to disable the guardrail.

Everything else works out of the box.

## What to expect

**Most prompts will fall back to the heuristic ladder.** Only `coding` and `long-context` currently have measured cells clearing the confidence floor, so the other five work-types will say "no measured cell above the confidence floor" and suggest the ladder instead. That is the floor doing its job, not a malfunction. See `meta.coverage` in `routing-table.json`.

**Named models are suggestions, not requirements.** The ladder names Grok, Gemini, and GPT tiers alongside Claude. If you do not have those CLIs installed and authenticated, ignore those suggestions; the injected text says so too. Nothing breaks, you just stay on Claude.

**The numbers are one person's measurements.** Read "What the table is, and what it is not" in the README before you weight them heavily. Short version: n is 2 to 5 tasks per cell, only the coding cells come from a real codebase, and the confidence floor exists precisely because the data is thin.
