#!/usr/bin/env python3
"""UserPromptSubmit hook: routing gate (Tier 2a, expanded work-types).

Keyword-gated, no API call. Classifies the prompt into a work-type, consults the
measured routing table (model-router/routing-table.json), and injects a concrete,
evidence-backed routing recommendation. Answer-path work-types (reasoning /
long-context / grounded-qa / extraction) are included because that is where
Gemini/Grok win the benchmark.

Design rules (see Fable review, 2026-07-15):
  - GUARDRAIL FIRST: style-locked domains -> Claude only, override everything.
  - Match the INSTRUCTION, not a pasted payload: strip fenced code blocks and
    head-truncate before keyword matching; total length is a separate long-context
    signal (suppressed when coding keywords are present).
  - First-match chain ordered by precision, with answer-path/question intent BEFORE
    the broad coding nouns, and planning before coding.
  - Word boundaries everywhere; prefer multi-word phrases over ambiguous single words.
  - Conversational turns stay SILENT (ack short-circuit + interrogative blacklist).
  - Consume the deterministic part of the router (classify + above-floor candidate
    set + Frugal/Fast picks). Do NOT auto-break a measured tie: ties go to the user
    via AskUserQuestion per the router contract; the final mode-pick stays in
    /smart-route.

Fail-open: any error, missing table, unclassifiable or non-matching prompt exits 0
with no output, so a broken gate never blocks a prompt.
"""
import sys
import json
import re
import os

# Derive the table path relative to this hook (hooks/ and skills/ are siblings
# under .claude/), so the repo stays portable. Absolute for the shell CWD.
TABLE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "skills", "model-router", "routing-table.json",
)

BAR = 0.5
FLOOR_MIN_N = 3
FLOOR_CI_MULT = 0.6
FAST_TIE_FRAC = 0.15
LONG_CTX_CHARS = 4000
HEADER = "ROUTING GATE (auto-injected)"

I = re.IGNORECASE

# --- pre-chain short-circuits (stay silent) --------------------------------

# Pure acknowledgements / opinion asks: match only when they ARE the whole message.
ACK = re.compile(
    r"^(thanks?|thank you|thx|ty|ok(ay)?|k|yes|yep|yeah|no|nope|nah|sure|great|nice|"
    r"perfect|awesome|cool|got it|sounds good|looks good|lgtm|go ahead|do it|"
    r"yes,? do it|please do|makes sense|agreed|correct)[\s.!,]*$",
    I,
)
OPT_OUT = re.compile(
    r"(no route|no routing|don'?t route|do not route|skip rout|main model only|keep this on opus)",
    I,
)

# --- guardrail: style-locked domains (Claude only) -------------------------

# EDIT THIS for your org. These are domains where a locked voice, methodology or
# brand matters more than any measured score, so the gate refuses to route them
# out no matter what the table says. To disable the guardrail, set it to None.
#
# Use MULTI-WORD phrases only. Single words like "compliance", "clinical",
# "medical", "patient", "fiction" or "prose" read as style-locked in isolation but
# are ordinary vocabulary in a coding prompt: "add a compliance check to the CI
# pipeline" and "be patient, first run the failing tests" both matched an earlier
# single-word version of this list and had their routing silently suppressed. A
# guardrail that fires on normal work is worse than none, because it trains people
# to turn it off.
STYLE_LOCKED = re.compile(
    r"\b(brand voice|house style|tone of voice|in (my|our) voice|"
    r"legal (copy|review|opinion)|contract (drafting|language)|"
    r"press release|marketing copy|ad copy|book blurb|back cover|"
    r"ghostwrit\w*|book (prose|manuscript))\b",
    I,
)

# --- code-review -----------------------------------------------------------

REVIEW = re.compile(
    r"\b(code ?review|review (the |this |my )?(pr|pull request|diff|code|change)|"
    r"pull request review|review pull request|pr ?#?\d+|"
    r"any (issues|problems) with this (code|diff)|critique this (function|implementation|code)|"
    r"second pair of eyes|nitpick|audit (the |this )?(code|diff|change))\b",
    I,
)

# --- extraction ------------------------------------------------------------

EXTRACT = re.compile(
    r"(\bextract (the|all|every|each)\b.*\bfrom\b|"
    r"\binto (json|csv|yaml|a table|a spreadsheet)\b|\bas (json|csv|a table)\b|\bto csv\b|"
    r"\bstructured data\b|\bpull out (the|all)\b|\bparse (this|these|the)\b.*\binto\b|"
    r"\blist (all|every)\b.*\b(in|from) (this|the) (text|doc|document|file|page)\b|"
    r"\b(emails?|phone numbers?|dates|urls?|names) from\b|\bnamed entit|\bkey.value pairs\b|\btabulate\b)",
    I,
)
# Refactor-speak / "write a parser" => coding, not extraction.
EXTRACT_TO_CODE = re.compile(
    r"\bextract (a |an |the |this |that |its |your )?(method|function|class|component|helper|variable|module|interface)\b|"
    r"\b(write|implement|build|create) (a |an )?(parser|scraper|extractor)\b",
    I,
)

# --- long-context ----------------------------------------------------------

LONGCTX = re.compile(
    r"(summariz\w* (this|the|these|that) (doc|document|pdf|paper|report|transcript|thread|article|book|chapter|file)|"
    r"\btl;?dr\b|key points (from|of)|executive summary|across these (docs|documents|files|sources)|"
    r"condense (this|the)|based on the attached|from the transcript|"
    r"what does the (doc|document|report|paper) say)",
    I,
)

# --- reasoning (require math/logic context; bare 'solve'/'how many' excluded) ---

REASONING = re.compile(
    r"(\bprove (that|or disprove)\b|\bsolve for\b|solve (this|the) (equation|puzzle|riddle)|"
    r"how many (ways|combinations|permutations|possible)|probability (of|that)|\bodds (of|that)\b|"
    r"expected value|\bderivative\b|\bintegral\b|\btheorem\b|\bsyllogism\b|\bfallacy\b|"
    r"logic puzzle|brain teaser|\bdeduce\b|\bcounterexample\b|(valid|sound) argument|"
    r"which conclusion follows)",
    I,
)

# --- grounded-qa (web) vs local-lookup (repo/files) ------------------------

WEB_QA = re.compile(
    r"(look up|search the web|\bgoogle\b (it|this|that|for)|latest version of|"
    r"what'?s the latest [a-z]+ (release|version)|current price|stock price|recent news|"
    r"as of (today|202\d)|up.?to.?date|cite (your )?sources|with citations|who won|"
    r"release date|is \w+ still (supported|maintained|available))",
    I,
)
INTERROGATIVE = re.compile(
    r"^(what|which|who|when|where|how (much|many|old|long))\b",
    I,
)
QA_BLACKLIST = re.compile(
    r"(what do (you|we)|what'?s your|what should|what about|what if we|what'?s next|"
    r"the latest on|any thoughts)",
    I,
)
LOCAL_REF = re.compile(
    r"\b(this (repo|repository|project|codebase|file|code|module|function|app|package|component)|"
    r"\bhere\b|our (code|repo|project)|the codebase)\b",
    I,
)

# --- planning (before coding so 'implementation plan' isn't stolen) ---------

PLAN = re.compile(
    r"(\barchitect\b|design (a|the|this|an) |\bspec out\b|write a spec|design doc|"
    r"\broadmap\b|break (this|it|down)|\bdecompose\b|scope out|trade-?offs?|"
    r"implementation plan|system design|migration plan|\brollout\b|\bmilestone\b|"
    r"\brfc\b|\bproposal\b|requirements|high-level approach|tech stack|"
    r"user stor(y|ies)|estimate the (effort|work)|\bwaves?\b|\bappetite\b|"
    r"plan (the|out|a) )",
    I,
)

# --- coding (broadest; last among positive buckets) ------------------------

CODE = re.compile(
    r"\b("
    r"refactor|implement|debug|codebase|function|classes?|method|module|"
    r"api|endpoint|unit ?test|pytest|typecheck|compile|build |rebuild|migrat|"
    r"regex|typescript|javascript|python|rust|react|tauri|fastapi|vite|webpack|"
    r"backtest|strateg|adapter|parser|schema|deploy|wire ?up|integrat|"
    r"stack ?trace|traceback|error message|\bbug\b|segfault|null pointer|\bNaN\b|"
    r"npm|\bpip\b|cargo|docker|\bgit\b|merge conflict|rebase|lint|eslint|mypy|ruff|"
    r"write a script|\bsql\b|dependency|package|commit|branch|\bmock\b|fixture|stub|"
    r"powershell|failing test|fix (the |this )?(bug|test|error)"
    r")\b",
    I,
)
# Imperative coding verbs (used for the extraction->coding tie-break).
CODE_IMPERATIVE = re.compile(r"\b(write|implement|build|create|refactor|add) (a |an |the )?", I)


def classify(instr, long_by_length):
    if STYLE_LOCKED and STYLE_LOCKED.search(instr):
        return "style-locked"
    if REVIEW.search(instr):
        return "code-review"
    if EXTRACT_TO_CODE.search(instr):
        return "coding"  # "extract this function/component", "write a parser" => coding
    if EXTRACT.search(instr):
        return "extraction"
    if LONGCTX.search(instr) or long_by_length:
        return "long-context"
    if REASONING.search(instr):
        return "reasoning"
    # grounded-qa / local-lookup
    if WEB_QA.search(instr):
        return "grounded-qa"
    if INTERROGATIVE.search(instr) and not QA_BLACKLIST.search(instr) and len(instr.split()) >= 5 \
            and not CODE_IMPERATIVE.search(instr):
        return "local-lookup" if LOCAL_REF.search(instr) else "grounded-qa"
    if PLAN.search(instr):
        return "planning"
    if CODE.search(instr):
        return "coding"
    return None


# --- table consumption -----------------------------------------------------

def load_cells():
    try:
        with open(TABLE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh).get("cells", [])
    except Exception:
        return None


def candidates_for(cells, work_type):
    out = []
    for c in cells:
        if c.get("work_type") != work_type or c.get("did_not_solve"):
            continue
        pk, n = c.get("pass_at_k"), c.get("n")
        lo, hi, val = c.get("ci_low"), c.get("ci_high"), c.get("validity")
        if None in (pk, n, lo, hi, val):
            continue
        if pk < BAR or n < FLOOR_MIN_N or (hi - lo) > FLOOR_CI_MULT * val:
            continue
        out.append(c)
    return out


def _cost(c):
    v = c.get("cost_per_solved_usd")
    return 0.0 if v is None else v


# --- messages --------------------------------------------------------------

TAIL = (
    "Delegate only if the task is self-contained and cheaply verifiable "
    "(tests pass / diff compiles / schema validates / answer checkable); otherwise keep "
    "it on the main model and say why in one sentence. Ignore any provider you do not "
    "have installed and authenticated; a named model is a suggestion, not a requirement."
)
ANSWER_PATH = {"reasoning", "long-context", "grounded-qa", "extraction"}


def _cheapest_set(cells):
    """Models at the minimum cost among `cells`.

    A null `cost_per_solved_usd` means the cost was never captured, NOT that the
    model is free. `_cost` collapses both to 0.0 for ordering, so the winning set
    can contain models whose cost is simply unknown. Report that honestly instead
    of calling them cheapest: the table's own `meta.cost_basis` distinguishes 0.0
    (flat-rate covered) from null (not captured), and so should this message.
    """
    m = min(_cost(c) for c in cells)
    winners = [c for c in cells if _cost(c) == m][:4]
    any_uncosted = any(c.get("cost_per_solved_usd") is None for c in winners)
    return [c["model"] for c in winners], m, any_uncosted


def msg_measured(work_type, cands):
    n = len(cands)
    top_pk = max(c["pass_at_k"] for c in cands)

    # Frugal = cheapest above-floor cell(s).
    frugal, min_cost, uncosted = _cheapest_set(cands)
    if uncosted:
        cost_note = "cost NOT captured, so unranked on cost - choose deliberately"
    elif min_cost == 0.0:
        cost_note = "flat-rate covered"
    else:
        cost_note = f"~${min_cost:.3f}/solved"
    frugal_tie = ""
    if len(frugal) > 1:
        frugal_tie = " [UNRANKED: cost not captured]." if uncosted else " [MEASURED TIE]."
    frugal_line = f"Frugal ({cost_note}): {', '.join(frugal)}" + (frugal_tie or ".")

    # Fast = lowest median wall-time, tie within FAST_TIE_FRAC.
    walls = [(c["model"], c["median_wall_ms"]) for c in cands if c.get("median_wall_ms")]
    fast_line = ""
    if walls:
        fastest = min(w for _, w in walls)
        fast_set = [m for m, w in walls if w <= fastest * (1.0 + FAST_TIE_FRAC)][:4]
        fast_line = f" Fast (lowest latency ~{round(fastest / 1000.0)}s): {', '.join(fast_set)}."

    # Balanced (default) ADDITIONALLY requires ci_low >= BAR. If nothing clears it
    # (small-N CIs, e.g. reasoning/long-context), Balanced falls to the ladder -
    # do not overstate the measured pick. (Fix: PR#3 review, major 2.)
    elig = [c for c in cands if (c.get("ci_low") or 0.0) >= BAR]
    if elig:
        bset, _, bal_uncosted = _cheapest_set(elig)
        # A set that is only "tied" because nobody's cost was captured is not a
        # measured tie. Calling it one invites the reader to trust a number that
        # does not exist.
        tie = ""
        if len(bset) > 1:
            tie = " [UNRANKED: cost not captured]." if bal_uncosted else " [MEASURED TIE]."
        bal_line = (f" Balanced (default): {', '.join(bset)} "
                    f"(clears ci_low>={BAR})" + (tie or "."))
    else:
        bal_line = (
            f" Balanced (default): NO cell clears ci_low>={BAR} (small-N CIs), so Balanced "
            "falls to the heuristic ladder; the Frugal/Fast picks above apply to those modes.")

    return (
        f"{HEADER} - measured routing-table.json, work-type={work_type}: {n} cell(s) clear the "
        f"{BAR} pass@k bar above the confidence floor (top pass@k={top_pk}). "
        f"{frugal_line}{fast_line}{bal_line} "
        "Never auto-break a MEASURED TIE - surface the tied models to the user with "
        "AskUserQuestion per the router contract. " + TAIL
    )


def msg_below_floor(work_type):
    if work_type in ANSWER_PATH:
        ladder = (
            # Two separate corrections live in this string, both learned the hard way.
            #
            # 1. Bulk and grounded Q&A need DIFFERENT models. Flash-Lite cannot ground, so
            #    collapsing them sends a grounded question to a model that cannot ground --
            #    an ungrounded answer presented as grounded, which fails silently where a
            #    404 at least fails loudly.
            # 2. The bulk pin is 3.1, not 3.5. gemini-2.5-flash-lite and 2.0-flash-lite
            #    return HTTP 404, but gemini-3.5-flash-lite is NOT the replacement on this
            #    path: route-proof measures it through its own API key, while
            #    mcp__gemini__generate_text rejects it as "Unknown model". This line named
            #    3.5 for an hour after that was known, because the fact landed in the
            #    ai-routing skills and nobody carried it into the executable.
            #
            # This ladder renders only for a work-type in ANSWER_PATH -- reasoning,
            # long-context, grounded-qa, extraction -- and only when its cells fall below
            # the confidence floor. It never renders on coding, which clears the floor, so
            # a coding prompt cannot exercise it: that is precisely how a wrong model id
            # survived here while a "verified the hook" claim was made. Nor does it render
            # on style-writing, which the STYLE_LOCKED guardrail intercepts before
            # classification. Verify changes here against grounded-qa, extraction or
            # reasoning; long-context currently clears the floor but would render it too.
            "Fall back to the answer-path ladder - bulk extraction / classification -> "
            "Gemini 3.1 Flash-Lite (ultra-cheap, but NO grounding); grounded Q&A / anything "
            "needing current facts -> Gemini 2.5 Flash (grounding-capable); simple lookups "
            "-> Haiku 4.5. All via MCP `mcp__gemini__generate_text`. Gemini/Grok win "
            "answer-path in the benchmark; do not keep this on the main model by default."
        )
    else:
        ladder = (
            "Fall back to the heuristic ladder - well-specified coding w/ tests -> Grok 4.5; "
            "default agentic coding / review -> Claude Sonnet 5; hard multi-file / merge-critical "
            "-> Opus 4.8."
        )
    return (
        f"{HEADER} - work-type={work_type}: no measured cell above the confidence floor "
        f"(too few tasks / CI too wide). {ladder} " + TAIL
    )


def msg_local_lookup():
    return (
        f"{HEADER} - this reads as a LOCAL repo/file lookup (Tier-1 retrieval), not web-grounded "
        "Q&A. Delegate to a Haiku 4.5 subagent that READS the referenced local files (pass it the "
        "file paths) - do NOT send it to web Gemini, and do not burn the main model on a lookup. "
        "Keep it on the main model only if it needs full conversation context."
    )


def msg_planning():
    return (
        f"{HEADER} - this reads as complex-planning. Planning usually needs full conversation "
        "context (a Tier-3 / main-model pattern), so it is often NOT a delegatable measured "
        "work-type. Keep the planning itself on the main model, but if you can carve out a "
        "self-contained, verifiable coding sub-task, route THAT through the measured coding table "
        "(fastest measured coder: grok-4.5). "
        "Otherwise say why you are staying on the main model."
    )


def msg_style_locked():
    return (
        f"{HEADER} - GUARDRAIL: this touches a style-locked domain (see STYLE_LOCKED in "
        "routing_gate.py). Policy: incumbent model only - do NOT route out regardless of any "
        "measured score. Handle on Claude (Sonnet default, Opus/Fable for ceiling)."
    )


def msg_generic(work_type):
    return (
        f"{HEADER} - this reads as a {work_type} task, but the routing table could not be read. "
        "Run the router manually: classify the work-type and consult /smart-route, and "
        "delegate to Grok 4.5 / Fable 5 / Gemini / Haiku when self-contained and cheaply "
        "verifiable. " + TAIL
    )


def emit(text):
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}
    }))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    raw = (data.get("prompt") or "").strip()
    if len(raw) < 12 or raw.startswith("/") or OPT_OUT.search(raw) or ACK.search(raw):
        sys.exit(0)

    # Classify on the instruction, not a pasted payload.
    instr = re.sub(r"```.*?```", " ", raw, flags=re.DOTALL)[:600]
    long_by_length = len(raw) > LONG_CTX_CHARS and not CODE.search(instr) and not REVIEW.search(instr)

    work_type = classify(instr, long_by_length)
    if work_type is None:
        sys.exit(0)

    if work_type == "style-locked":
        emit(msg_style_locked())
    if work_type == "planning":
        emit(msg_planning())
    if work_type == "local-lookup":
        emit(msg_local_lookup())

    # coding / code-review / reasoning / long-context / grounded-qa / extraction -> table
    cells = load_cells()
    if cells is None:
        emit(msg_generic(work_type))

    cands = candidates_for(cells, work_type)
    emit(msg_measured(work_type, cands) if cands else msg_below_floor(work_type))


if __name__ == "__main__":
    # Blanket fail-open: any unexpected error (corrupt/odd-shaped table, etc.) exits 0
    # with no output. emit() raises SystemExit (not Exception), so normal output is
    # unaffected. (Fix: PR#3 review, major 1.)
    try:
        main()
    except Exception:
        sys.exit(0)
