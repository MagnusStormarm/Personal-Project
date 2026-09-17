#!/usr/bin/env python3
"""Decide what to do about an issue: weigh each candidate fix's
EFFECTIVENESS against its SESSION DRAW, with draw costed from run
artifacts on disk and budget read from recorded rate-limit observations.

THE PROCEDURE THIS SUPPORTS
---------------------------
  1. Search for information on the issue        (agent)
  2. Rank candidate fixes: effectiveness vs draw, against BOTH the
     short-window and long-window budgets         <- this script
  3. Apply the recommended fix                   (agent)
  4. Report findings                             (agent)
  5. Wait for user input                         (agent)

Steps 1, 3, 4 and 5 are agent actions; no script can do them. What a
script CAN do is step 2 without flattering itself: the draw numbers come
from what past runs actually spent, and the budget from what get_session
actually returned, so neither is a remembered figure.

WHY BOTH WINDOWS
----------------
rate_limit_info reports only the ONE window currently binding. It read
five_hour in the morning and, once that window reset, seven_day with a
reset four days out. A single snapshot therefore cannot show both, and
reading only the binding one is how a four-day constraint gets mistaken
for a four-hour one. This reads the per-window history the guard records
and prints every window it has ever seen, each labelled with the age of
its observation, so a stale entry cannot pass as current.

HOW CANDIDATES ARE SCORED, AND A DELIBERATE CHANGE
---------------------------------------------------
A free tier scores its effectiveness outright. A nested tier scores
effectiveness divided by its MEASURED sessions per run, so an 18-session
drift chain must be roughly four times as useful as a 4-session stress run
to outrank it.

The divisor used to be a flat `draw * 10` with draw hardcoded to 1 for
both nested tiers, which had two effects worth naming. It made tiers 3 and
4 rank as equally expensive when the artifacts on disk say otherwise, and
it made ANY free option beat ANY nested one -- an effectiveness-1
re-reading outranked an effectiveness-5 run that would actually settle the
question. That is not "the cheapest option that can still answer the
question"; it is the cheapest option regardless of whether it answers
anything. Now a weak free option can lose to a strong nested one WHEN THE
BUDGET ALLOWS IT. When the budget does not -- the usual case -- nested
tiers are excluded outright and the free option wins by default, which is
the behaviour that actually matters day to day.

WHAT IT REFUSES TO ESTIMATE
---------------------------
Tokens, dollars, and any "percent remaining". Nothing on disk supports
them and no remaining-figure is exposed to a session. A confident number
here would be worse than no number, because it would get quoted back.

Effectiveness is the one judged input and is labelled as such. The script
does not pretend to derive it -- it makes the judgement explicit and
puts it next to a measured cost, which is the whole value.

Usage:
    python3 scripts/session_cost_guide.py                    # tiers + budget
    python3 scripts/session_cost_guide.py --rank fixes.json  # rank candidates
"""
import argparse
import glob
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "saves" / "exports"
REPO = ROOT.parent
HISTORY_FILE = REPO / ".claude" / "rate_limit_history.json"
ISSUES_FILE = ROOT / "docs" / "open_issues.json"

# Draw weight per tier. Not a token count -- nested `claude -p` sessions,
# the quantity that actually moves the rate limit. Tiers 0-2 spawn none.
#
# Tiers 3 and 4 used to be hardcoded to 1 apiece, which threw away a
# difference this script already measures: over the runs on disk, tier 3
# averaged 3.8 sessions per run and tier 4 averaged 6.0, and a DEFAULT
# drift chain is 18. Ranking them as equally expensive meant the costlier
# option could win a tie it should have lost. measured_draw() replaces the
# guess with the artifacts, and falls back to the old constants only when
# there is nothing on disk to measure.
FREE_TIER_DRAW = {0: 0, 1: 0, 2: 0}
FALLBACK_DRAW = {3: 4.0, 4: 18.0}

FREE_TIERS = [
    (0, "Re-analyse run artifacts already on disk",
     "retained campaign copies, continuity_notes, journal, per-turn git history"),
    (1, "Run project tooling against an existing campaign copy",
     "playtest_audit.py, validate_state.py, prune_advisor.py, gm_cases.py"),
    (2, "Unit-test predicates against synthetic states",
     "no model involved at all"),
]


def measured_draw(sp_secs_runs, dc_secs_runs):
    """Sessions per run for the nested tiers, measured from disk.

    Returns {tier: sessions_per_run}. A tier with no runs on disk keeps its
    fallback, because "unmeasured" must not read as "free" -- that is the
    same fail-open this file was already guilty of on the budget check.
    """
    draw = dict(FREE_TIER_DRAW)
    for tier, (sessions, runs) in ((3, sp_secs_runs), (4, dc_secs_runs)):
        draw[tier] = (sessions / runs) if runs else FALLBACK_DRAW[tier]
    return draw


def measure(pattern, session_key):
    runs = sessions = 0
    secs = []
    for f in sorted(glob.glob(str(EXPORTS / pattern))):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        runs += 1
        for rec in session_key(d):
            sessions += 1
            s = rec.get("seconds")
            if isinstance(s, (int, float)):
                secs.append(s)
    return runs, sessions, secs


def fmt(secs):
    if not secs:
        return "no runs on disk yet"
    return (f"{len(secs)} session(s), {min(secs):.0f}-{max(secs):.0f}s each "
            f"(~{sum(secs)/60:.0f} min total)")


def window_horizon(window, rec):
    """Roughly how long this window's constraint lasts, in seconds.

    Used to rank windows by how much a warning on them actually costs. A
    warning you wait out over lunch and one that blocks the rest of the
    week are the same STATUS and completely different decisions, so status
    alone must not drive the verdict. Read from the name where it is
    recognisable, else inferred from the recorded reset distance.
    """
    name = str(window or "").lower()
    if "week" in name or "seven_day" in name or "7_day" in name:
        return 7 * 86400
    if "day" in name:
        return 86400
    if "hour" in name:
        for tok in name.replace("_", " ").split():
            if tok.isdigit():
                return int(tok) * 3600
        return 3600
    resets, rec_at = rec.get("resets_at"), rec.get("recorded_at")
    if resets and rec_at:
        return max(int(resets) - int(rec_at), 0)
    return 0


def is_long_window(window, rec):
    """A window whose constraint outlasts a working session.

    The distinction that matters: a short window can be waited out today,
    a long one cannot, so only a long window's clearance is real clearance
    for an expensive run.
    """
    return window_horizon(window, rec) >= 86400


def budget():
    """Every window ever observed, each with the age of its observation.

    Returns (rows, worst_status). A window whose reset time has already
    passed is reported as expired rather than as a live constraint --
    that is exactly the five_hour entry that misled once already.
    """
    # "unknown" is returned rather than None, and callers treat it as
    # blocking. An earlier version returned None here and rank_fixes()
    # computed `blocked = worst is not None and worst != "allowed"`, so a
    # missing or unreadable history file meant NOT blocked: with no budget
    # information at all, an 18-session drift chain was RECOMMENDED outright
    # with no warning. That is fail-open on the one control the whole cost
    # discipline rests on, and no-budget-recorded is the NORMAL state at the
    # start of a session, not an edge case. Fail-safe defaults: an
    # unrecognized or missing input is invalid, not permissive.
    if not HISTORY_FILE.exists():
        return [], "unknown"
    try:
        hist = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], "unknown"

    now = int(time.time())
    rank = {"allowed": 0, "allowed_warning": 1}
    rows, worst, worst_n, worst_h = [], "unknown", -1, -1
    long_seen = False
    # Longest horizon first. Ordering used to be alphabetical, which put
    # five_hour above seven_day and buried the window that actually decides
    # whether an expensive run can happen this week.
    ordered = sorted(hist.items(),
                     key=lambda kv: -window_horizon(kv[0], kv[1]))
    for window, rec in ordered:
        age = now - int(rec.get("recorded_at") or 0)
        resets = rec.get("resets_at")
        if resets and int(resets) > now:
            left = int(resets) - now
            when = f"resets in {left // 86400}d {(left % 86400) // 3600}h"
            live = True
        elif resets:
            when = "that reset has PASSED -- re-check before trusting"
            live = False
        else:
            when = "no reset time recorded"
            live = False
        status = str(rec.get("status") or "?")
        rows.append((window, status, when, age, live))
        h = window_horizon(window, rec)
        if live and is_long_window(window, rec):
            long_seen = True
        n = rank.get(status, 2)
        # Worse status wins; on a TIE the longer horizon wins, because
        # "warning, clears in two hours" and "warning, clears in four days"
        # were previously indistinguishable and the alphabet decided which
        # got reported as binding.
        if live and (n > worst_n or (n == worst_n and h > worst_h)):
            worst, worst_n, worst_h = status, n, h

    if worst_n < 0:
        return rows, "unknown"
    # A clear short window is NOT clearance. rate_limit_info reports only the
    # window currently binding, so a five_hour "allowed" observation says
    # nothing whatever about the weekly position -- and the weekly one is what
    # blocks a run for days. Observed directly today: the five-hour window
    # reset at midday and the seven-day window turned out to be binding, four
    # days out. Without this, one five_hour:allowed reading green-lit an
    # 18-session chain.
    if worst == "allowed" and not long_seen:
        return rows, "unknown-long"
    return rows, worst


def load_issues(path=None):
    p = Path(path) if path else ISSUES_FILE
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return d.get("issues", d) if isinstance(d, dict) else d


def inventory(issues):
    """Open issues, with what is known and what is deliberately not scored.

    Deliberately NOT a ranking. An issue whose candidates carry no
    effectiveness score has not been researched, and inventing one here
    would read as a measurement the next time anyone looks.
    """
    open_ = [i for i in issues if i.get("status") != "fixed"]
    fixed = [i for i in issues if i.get("status") == "fixed"]
    print(f"\nOPEN ISSUES ({len(open_)} open, {len(fixed)} fixed):")
    if not open_ and not fixed:
        print("  (none tracked -- see docs/open_issues.json)")
    for i in open_:
        owner = i.get("owner", "?")
        mark = "[YOURS]" if owner == "user-decision" else "[agent]"
        cands = i.get("candidates") or []
        scored = [c for c in cands if c.get("effectiveness") is not None]
        state = (f"{len(scored)}/{len(cands)} candidate(s) scored" if cands
                 else "no candidates yet -- not researched")
        print(f"\n  {mark} {i.get('id')}")
        print(f"     {i.get('summary','')[:100]}")
        print(f"     {state}")
        if owner == "user-decision":
            print("     not scored on purpose: this was put to the user as a design call")
    for i in fixed:
        print(f"\n  [done ] {i.get('id')}  ({i.get('fixed_by','')})")
    return open_


def rank_fixes(path, rows, worst, tier_draw):
    """Rank candidate fixes by effectiveness against draw.

    Each candidate: {name, tier, effectiveness (1-5), why, notes}.
    Effectiveness is a JUDGED input -- the script prints it as given and
    labels it judged. Draw is measured.
    """
    if path and path != "-":
        with open(path, encoding="utf-8") as fh:
            cands = json.load(fh)
    else:
        cands, skipped = [], []
        for i in load_issues():
            if i.get("status") == "fixed":
                continue
            if i.get("owner") == "user-decision":
                skipped.append(i.get("id"))
                continue
            for c in (i.get("candidates") or []):
                if c.get("effectiveness") is None:
                    skipped.append(f"{i.get('id')}/{c.get('name')} (unscored)")
                    continue
                c = dict(c, name=f"{i.get('id')}: {c.get('name')}")
                cands.append(c)
        if skipped:
            print("\n  NOT RANKED, on purpose:")
            for s in skipped:
                print(f"    - {s}")
        if not cands:
            print("\n  Nothing rankable yet. Research an issue and add scored")
            print("  candidates to docs/open_issues.json first.")
            return []

    blocked = worst != "allowed"   # unknown and unknown-long block too
    print(f"\n{'':2}{'CANDIDATE':<34} {'TIER':>4} {'EFFECT':>7} {'DRAW':>6}  VERDICT")
    print("  " + "-" * 84)

    scored = []
    for c in cands:
        tier = int(c.get("tier", 0))
        eff = int(c.get("effectiveness", 0))
        draw = tier_draw.get(tier, FALLBACK_DRAW.get(tier, 1.0))
        # Free tiers cannot divide by zero and are simply best-in-class for
        # any effectiveness above nil. Among nested tiers, effectiveness is
        # divided by MEASURED sessions per run, so an 18-session chain must
        # be roughly four times as effective as a 4-session stress run to
        # outrank it -- which is the trade the old flat weight hid.
        score = eff if draw == 0 else eff / draw
        permitted = not (blocked and tier >= 3)
        scored.append((score, permitted, tier, eff, c, draw))

    # Ties are broken toward LOWER churn, and only ONE candidate is ever
    # marked. An earlier version marked every candidate matching the top
    # score, so two mutually exclusive fixes both came back "RECOMMENDED"
    # -- which is not a ranking, it is a restatement of the problem.
    # `churn` is a judged input like effectiveness: how much existing data
    # or interface the fix breaks. Absent, it counts as 0.
    scored.sort(key=lambda r: (r[1], r[0], -int(r[4].get("churn", 0))),
                reverse=True)
    top = scored[0] if scored and scored[0][1] else None
    for row in scored:
        score, permitted, tier, eff, c, draw = row
        verdict = ("" if permitted else
                   ("BLOCKED: budget unknown" if worst == "unknown"
                    else "BLOCKED: weekly window unobserved"
                    if worst == "unknown-long" else "BLOCKED by budget"))
        if top is not None and row is top:
            verdict = "<= RECOMMENDED"
        draw_s = ("none" if draw == 0 else f"{draw:.0f}/run")
        print(f"  {c.get('name','?')[:34]:<34} {tier:>4} {eff:>6}/5 {draw_s:>6}  {verdict}")
        if c.get("why"):
            print(f"    why: {c['why']}")
    print("\n  EFFECT is judged, not measured -- it is the author's estimate of how")
    print("  much of the issue the fix actually removes. TIER and DRAW are measured.")
    if worst == "unknown-long":
        print("  Tier 3+ candidates are excluded: only a SHORT window has been")
        print("  observed. A clear five-hour window says nothing about the weekly")
        print("  one, and the weekly one is what blocks a run for days.")
    elif worst == "unknown":
        print("  Tier 3+ candidates are excluded: NO usable budget observation.")
        print("  Record one before ranking an expensive run -- get_session ->")
        print("  external_metadata.rate_limit_info, then tier34_guard.py --record.")
    elif blocked:
        print(f"  Tier 3+ candidates are excluded: budget status is {worst!r}.")
    return [c for _, p, _, _, c, _d in scored if p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", metavar="FIXES.json", nargs="?", const="-",
                    help="Rank candidates by effectiveness against draw. With no "
                         "argument, reads docs/open_issues.json.")
    ap.add_argument("--inventory", action="store_true",
                    help="List tracked open issues without ranking them.")
    args = ap.parse_args()

    print("Work available here, cheapest first. "
          "Do the cheapest option that can still answer the question.\n")
    for tier, what, detail in FREE_TIERS:
        print(f"  TIER {tier}  [no nested sessions]  {what}")
        print(f"          {detail}")
    print()

    sp_runs, sp_sessions, sp_secs = measure(
        "stress_transcript_*.json",
        lambda d: d.get("results", []) if isinstance(d, dict) else [])
    dc_runs, dc_sessions, dc_secs = measure(
        "drift_chain_*.json",
        lambda d: [t for c in d.get("chains", []) for t in c.get("turns", [])])
    print(f"  TIER 3  [ONE NESTED SESSION PER CASE]  run_stress_prompts.py")
    print(f"          measured over {sp_runs} run(s): {fmt(sp_secs)}")
    print(f"  TIER 4  [ONE NESTED SESSION PER TURN PER CHAIN]  run_drift_chain.py")
    print(f"          measured over {dc_runs} run(s): {fmt(dc_secs)}")
    if dc_secs:
        print(f"          a default 3x6 run = 18 sessions "
              f"~{18*(sum(dc_secs)/len(dc_secs))/60:.0f} min at the measured mean")
    print()

    rows, worst = budget()
    print("BUDGET -- every window observed, with the age of each observation:")
    if not rows:
        print("  (none recorded yet)")
        print("  Record one: get_session -> external_metadata.rate_limit_info, then")
        print("  python3 .claude/hooks/tier34_guard.py --record <status> <window> <resetsAt>")
    for window, status, when, age, live in rows:
        mark = "  " if live else "! "
        print(f"  {mark}{window:<12} {status:<16} {when:<44} "
              f"(observed {age // 60} min ago)")
    # Name the window and the wait, not just the status. "allowed_warning"
    # alone was printed for both a two-hour hold and a four-day one -- the
    # same words for the two decisions furthest apart in consequence.
    if worst == "unknown-long":
        print("\n  BINDING: the weekly window has NOT been observed. Only a short")
        print("  window is on record, and a clear short window is not clearance --")
        print("  rate_limit_info reports one window at a time. Tier 3 and 4 are OFF")
        print("  until a day-or-longer window is recorded.")
    elif worst == "unknown":
        print("\n  BINDING: no usable observation at all. Tier 3 and 4 are OFF.")
    elif worst != "allowed":
        binding = next(((w, when) for w, s, when, _a, live in rows
                        if live and s == worst), None)
        where = f" on {binding[0]} ({binding[1]})" if binding else ""
        print(f"\n  BINDING: {worst!r}{where} -- tier 3 and 4 are OFF. "
              f"Do tier 0-2 work.")
        if binding and binding[0] and "day" in binding[0].lower():
            print("  This is the WEEKLY window: it cannot be waited out inside a")
            print("  session. Plan the expensive run for after that reset.")
    else:
        longest = rows[0][0] if rows else "?"
        print(f"\n  All observed windows allowed, longest observed: {longest}.")
    print("  No remaining-percentage or token budget is exposed to a session;")
    print("  none is estimated here.")

    if args.inventory or args.rank:
        inventory(load_issues())
    if args.rank:
        rank_fixes(args.rank, rows, worst,
                   measured_draw((sp_sessions, sp_runs), (dc_sessions, dc_runs)))

    copies = sorted(glob.glob("/tmp/eldara-chain-*/eldara/saves/current.json")) + \
        sorted(glob.glob("/tmp/eldara-stress-*/eldara/saves/current.json"))
    if copies:
        print(f"\nRETAINED CAMPAIGN COPIES: {len(copies)} on disk -- tier 0 "
              "material, already paid for.")
        print("  Whether these are still worth mining is NOT something this script")
        print("  can know; it sees files, not what has been read. This heading used")
        print("  to assert they were UNMINED, which went on being printed after they")
        print("  had been read exhaustively -- a claim that is sometimes false trains")
        print("  you to skip the heading entirely. Check the found_by fields in")
        print("  docs/open_issues.json for what has already been drawn from them.")
        for c in copies:
            try:
                with open(c, encoding="utf-8") as fh:
                    s = json.load(fh)
                d = s.get("in_world_date") or {}
                print(f"  - turn {s.get('turn')}, day {d.get('day')} "
                      f"{d.get('month')}, {len(s.get('continuity_notes') or [])} "
                      f"note(s)  {os.path.dirname(os.path.dirname(c))}")
            except (OSError, json.JSONDecodeError):
                print(f"  - (unreadable) {c}")


if __name__ == "__main__":
    main()
