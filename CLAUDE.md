# Working rules for this project

## Rank work by results-per-draw before starting it

Some work here spawns nested `claude -p` sessions. That is by far the most
expensive thing this project does, and the cost is invisible until the
rate limit warns. Before starting anything, rank the available options by
**findings per unit of session draw**, and say which tier the chosen one
is in. Do the cheapest option that can still answer the question.

Run `python3 eldara/scripts/session_cost_guide.py` for the tiers with
costs recomputed from the run artifacts actually on disk. Do not copy
those numbers back into this file — one source of truth, recomputed, is
the whole point; a hardcoded table here would drift out of date exactly
the way this project exists to catch.

| Tier | Draw | What |
|---|---|---|
| 0 | none | Re-analysing run artifacts already on disk |
| 1 | none | Project tooling (`playtest_audit.py`, `validate_state.py`, `prune_advisor.py`, `gm_cases.py`) against an existing campaign copy |
| 2 | none | Unit-testing predicates against synthetic states |
| 3 | **high** | `run_stress_prompts.py` — one nested session **per case** |
| 4 | **highest** | `run_drift_chain.py` — one nested session **per turn per chain** |

**Tier 0 has repeatedly beaten tier 4 on findings per minute.** The single
best finding of the drift-chain work (`deadline_turn` counts turns while
the fiction dates obligations in days, and the two diverge 6x to
unbounded) came from re-reading artifacts already produced, not from a
new run. Assume the last expensive run is still under-mined before paying
for another.

Corollary: when an expensive run completes, mine it to exhaustion before
proposing a repeat. Check the retained campaign copies, `continuity_notes`,
the journal, and the per-turn git history — all of it is already paid for.

Do not rely on memory for what is still unmined. The first run of
`session_cost_guide.py` listed **eight** retained campaign copies when I
believed there were three; five were from earlier stress runs and had
been forgotten inside the same session that made them. The script lists
them every time for that reason.

## Check the budget before tier 3 or 4

`get_session` (claude-code-remote MCP, `session_id` omitted) returns
`external_metadata.rate_limit_info`. Read `status` before starting a
nested-session run:

- `allowed` — proceed.
- `allowed_warning` — **do not start a tier 3 or 4 run.** Report the
  reset time and offer tier 0-2 work instead.
- anything else — stop and report.

**Read `rateLimitType` too — it changes.** This field reports whichever
window is currently binding, not a fixed one. It was observed as
`five_hour` and then, once that window reset, as `seven_day` with a reset
four days out. An earlier version of this file claimed only a rolling
five-hour window existed and that weekly figures were unreachable; that
was wrong, and it was wrong in the expensive direction — it would have
read a multi-day constraint as one that clears this afternoon.

So report `status`, `rateLimitType` and `resetsAt` together. "Warning,
resets in four hours" and "warning, resets in four days" are the same
status and completely different decisions.

**A clear SHORT window is not clearance.** Because only one window is
reported at a time, a `five_hour: allowed` reading says nothing about the
weekly position — and the weekly one is what blocks a run for days.
`session_cost_guide.py` refuses to treat a short-window-only observation
as permission for tier 3 or 4, and where two windows tie on status it
names the longer-horizon one as binding. Before an expensive run, make
sure a day-or-longer window has actually been observed.

What is still true: there is no remaining-percentage or token-budget
number anywhere reachable, and nothing on disk carries live rate-limit
state (`~/.claude.json` has only feature flags). Do not invent a
remaining figure, and do not extrapolate one window's number into
another's.

`scripts/session_cost_guide.py` prints the tier table with costs
recomputed from whatever run artifacts are actually on disk, so the
numbers above stay honest as more runs accumulate.

## Report, then wait

After a final report, stop and wait for input before acting. This rule is
about *choosing well* when asked to proceed — it is not licence to start
work unprompted.

## Containment (non-negotiable)

The live campaign at `eldara/saves/` is **never** the working directory
for a test. Every harness here runs against a throwaway copy with no git
remote, because these scripts commit and push. `run_drift_chain.py` and
`run_stress_prompts.py` both do this already; anything new must too.

## Evidence over reasoning

Measured results have beaten my predictions repeatedly in this repo —
including cases where I was confident and wrong about what a run would
show. Verify before claiming. A null result from an instrument with known
gaps is not evidence; fix the instrument first, then re-state the result.
