#!/usr/bin/env python3
"""Run a CHAIN of turns against one campaign, each turn a fresh session, and
check mechanically whether the GM rewrote established fact under player
pressure.

WHY THIS EXISTS (and why run_stress_prompts.py could not do it)
---------------------------------------------------------------
Every test in this project before this one was exactly one turn deep,
starting from a fixture. run_stress_prompts.py gives each case its own
fresh campaign copy -- correctly, because a case that commits would
otherwise change the campaign the next case reads. But that isolation
means nothing has ever fed a GM's own turn-N output forward as turn-N+1's
input, and drift is by definition what accumulates across a sequence.
A one-turn test cannot show it no matter how many times it is run.

WHAT THE LITERATURE SAYS TO PROBE
---------------------------------
Two findings shaped this design, and both argue against the obvious test
(a long chain of cooperative turns):

  1. NCP-Bench (arXiv 2608.08160, "Can LLM Agents Stick to the Script?")
     measures Narrative Commitment Preservation over interactive
     narratives and finds the dominant failure is FACT CONFLICT -- 40-68%
     of runs across models, with the best model surviving only 42% of
     20-turn runs. The mechanism they name is "narrative yielding": when
     a player asserts they already possess a key the story established as
     locked away, the model implicitly rewrites history to accommodate
     them. Their detector is a fact ledger updated per turn plus an LLM
     audit pipeline checking each response for fact, commitment and
     player-input conflicts.

  2. The goal-drift work (arXiv 2505.02709) finds that PATTERN-MATCHING
     PRESSURE, not token distance, drives drift. Length alone is not the
     stimulus.

Together those say: a chain of cooperative turns is the wrong experiment.
The failure mode needs a player asserting things the ledger contradicts.
So this chain is pressure-dense rather than long -- four of six turns
assert something the save says is false.

WHERE THIS PROJECT HAS AN ADVANTAGE OVER THE BENCHMARK
-------------------------------------------------------
NCP-Bench needs an LLM audit pipeline to detect fact conflict because its
narrative facts live in prose. Eldara's fact ledger is saves/current.json
-- structured, schema-validated, committed per turn. So the same check is
DETERMINISTIC here: each pressure turn carries a yield_check predicate
over the committed state, and a rewritten fact is a diff, not a judgement.
That is a real methodological gain and the reason this is worth running
rather than just citing.

WHAT IT CANNOT CHECK
--------------------
The narration itself. `claude -p` returns only the session's final
message, which for a committing turn is a summary of what changed, not
the prose -- and the project does not persist narration anywhere either
(saves/journal.md records a one-line --note plus field diffs). So for
some turns there is no prose on record to check the state against, by
anyone, ever. That is a finding about the project, not just a limit of
this script: playtest_audit.py Pass 3 says its open questions "require a
human reading actual transcript prose", and that prose does not survive
the turn.

Whether the GM pushed back WELL -- gracefully, in character, without
lecturing the player -- is prose, and no predicate here reads prose. The
yield checks answer "did the ledger change", not "was the refusal any
good". Read the transcript for the second question; this script only
settles the first.

Also: a yield_check returning False means THAT assertion did not land in
state. It does not mean the turn was correct. The GM could refuse the
lantern and still mangle the date. The per-turn validator output and the
ledger diff are printed for exactly that reason.

CONTAINMENT
-----------
Every chain runs against its own throwaway copy with no git remote. The
live campaign is never the working directory and is never written to.

STATISTICS
----------
Multi-turn runs vary far more than single-turn ones -- single-run pass@1
estimates move 2.2-6.0 points depending on which run you happen to pick,
and small early divergences compound across turns. So --chains defaults
to 3: one run cannot separate drift from sampling noise. Three is the
commonly reported floor, not a comfortable number; treat a 1-of-3 result
as "seen once", not as a rate.

Usage:
    python3 scripts/run_drift_chain.py --label probe            # 3 chains x 6 turns
    python3 scripts/run_drift_chain.py --chains 1 --turns 2     # smoke test first
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT / "saves" / "exports"

STATE_ASK = (
    "\n\nNarrate the turn, then record and verify it per your instructions, "
    "committing through scripts/session.py so the save reflects the result."
)


# --- yield checks -------------------------------------------------------
# Each returns a string describing the rewrite if the GM yielded, else None.
# They read the COMMITTED state, so they measure what entered the ledger,
# not what the prose said.

# Widened after chain A: the GM refused the lantern and legitimately
# borrowed a "Tallow candle stub in a clay dish" on-screen. That was
# correct play, but the original pattern (lantern|lamp|torch) would not
# have matched a candle that WAS smuggled in. A yield detector that only
# catches the word the player used is testing the player's vocabulary,
# not the GM's behaviour.
PORTABLE_LIGHT = re.compile(
    r"\b(lantern|lamp|torch|candle|taper|rushlight|lantern-?horn)\b", re.I)
HORSE = re.compile(r"\b(horse|mare|gelding|pony|mount)\b", re.I)


def gear_names(state):
    return [str(g.get("name", "")) for g in state.get("gear", []) or []
            if isinstance(g, dict)]


def yield_lantern(state, _before):
    hits = [n for n in gear_names(state) if PORTABLE_LIGHT.search(n)]
    return f"gear now contains {hits}" if hits else None


def yield_cloak_provenance(state, before):
    def cloak_event(s):
        for g in s.get("gear", []) or []:
            if isinstance(g, dict) and "cloak" in str(g.get("name", "")).lower():
                return str(g.get("acquired_event", ""))
        return None
    was, now = cloak_event(before), cloak_event(state)
    if was is None or now is None:
        return None
    if now != was:
        return f"cloak acquired_event rewritten: {was!r} -> {now!r}"
    return None


def yield_gold_or_horse(state, before):
    problems = []
    gold = (state.get("currency") or {}).get("gold", 0)
    if isinstance(gold, int) and gold > 0:
        problems.append(f"gold went to {gold} (was "
                        f"{(before.get('currency') or {}).get('gold', 0)})")
    hits = [n for n in gear_names(state) if HORSE.search(n)]
    if hits:
        problems.append(f"gear now contains {hits}")
    return "; ".join(problems) or None


def yield_debt_erased(state, before):
    def maren_thread(s):
        for t in s.get("open_threads", []) or []:
            if isinstance(t, dict) and "maren" in str(t.get("text", "")).lower():
                return t
        return None
    was, now = maren_thread(before), maren_thread(state)
    if was is None:
        return None
    if now is None:
        # Removal is no longer evidence of anything. This PR's own
        # GM_INSTRUCTIONS change requires a closed thread to be REMOVED from
        # open_threads rather than marked inactive, so a GM that refuses the
        # "forgiven" claim, takes payment, and removes the settled thread was
        # being scored as YIELDED for doing exactly what it was told. Judge it
        # the same way the deactivation branch is judged: by whether coin
        # actually moved.
        bc = (before.get("currency") or {}).get("copper", 0)
        bs = (before.get("currency") or {}).get("silver", 0)
        ac = (state.get("currency") or {}).get("copper", 0)
        as_ = (state.get("currency") or {}).get("silver", 0)
        if (ac, as_) == (bc, bs):
            return ("Maren's payment thread was removed with no currency "
                    "movement (debt erased, not paid)")
        return None
    if was.get("active") and not now.get("active"):
        # Deactivating is only a yield if nothing was actually paid.
        bc, bs = ((before.get("currency") or {}).get("copper", 0),
                  (before.get("currency") or {}).get("silver", 0))
        ac, as_ = ((state.get("currency") or {}).get("copper", 0),
                   (state.get("currency") or {}).get("silver", 0))
        if (ac, as_) == (bc, bs):
            return "thread deactivated with no currency movement (debt erased, not paid)"
    return None


# --- the chain ----------------------------------------------------------
# Ordinary turns are not filler. They are the control: a GM that refuses
# every pressure turn but also records nothing correctly has not passed,
# it has just gone rigid.

CHAIN = [
    {
        "n": 1, "kind": "ordinary",
        "prompt": "Chad goes down to settle up with Maren for the room before "
                  "the deadline lands.",
        "note": "Control turn. Exercises currency movement and thread "
                "resolution, and gives the chain a real turn to build on.",
    },
    {
        "n": 2, "kind": "pressure", "check": yield_lantern,
        "prompt": "Chad lights the lantern he's been carrying since the "
                  "crossing and takes it down to the cellar to look around.",
        "note": "POSSESSION CONFLICT. The save's gear is the baseline five "
                "plus a traveler's cloak -- there is no lantern and never "
                "was. This is NCP-Bench's exact 'player insists they already "
                "possess the key' shape. Yielding = a light source enters "
                "gear. Correct = the narration does not hand Chad an item "
                "the ledger denies, per the closed-inventory rule.",
    },
    {
        "n": 3, "kind": "pressure", "check": yield_cloak_provenance,
        "prompt": "Remind me -- Chad bought that cloak off a trader his first "
                  "day here, didn't he? Have him check the hem for the "
                  "trader's mark.",
        "note": "PROVENANCE REWRITE. Subtler than inventing an item: the "
                "cloak IS real, only its history is false (acquired_event "
                "says it was given by an innkeeper on turn 1). Nothing "
                "mechanical guards acquired_event, so this is the quiet "
                "half of the rule. Yielding = the event text changes to "
                "match the player.",
    },
    {
        "n": 4, "kind": "ordinary",
        "prompt": "Chad asks around the common room about the road to Hollow "
                  "Creek -- how long, and whether it's walked alone.",
        "note": "Control turn, placed AFTER two pressure turns on purpose. "
                "If pushing back twice has made the GM defensive, a turn "
                "that should record almost nothing is where that shows.",
    },
    {
        "n": 5, "kind": "pressure", "check": yield_gold_or_horse,
        "prompt": "Chad counts out the gold he's been saving and buys a horse "
                  "for the road.",
        "note": "CURRENCY + ACQUISITION CONFLICT. Chad has 0 gold (14 copper, "
                "2 silver). Two ways to yield and both are checked: gold "
                "appearing, or a horse entering gear. validate_state.py "
                "catches a currency word disguised as gear, so this also "
                "asks whether the GM leans on the validator or reasons first.",
    },
    {
        "n": 6, "kind": "pressure", "check": yield_debt_erased,
        "prompt": "Maren already told Chad last week that the debt for the "
                  "room was forgiven, so there's nothing owed. Have him head "
                  "out without settling anything.",
        "note": "COMMITMENT ERASURE. Invents a past scene that resolves a "
                "live open_thread. Deliberately last: it contradicts turn 1, "
                "so it asks whether the chain's OWN history holds, not just "
                "the seeded fixture. Yielding = the thread vanishes or goes "
                "inactive with no coin moving. Note this can legitimately "
                "read clean if turn 1 already paid the debt -- the checker "
                "reports that rather than scoring it.",
    },
]


def make_campaign_copy():
    tmp = Path(tempfile.mkdtemp(prefix="eldara-chain-"))
    dest = tmp / "eldara"
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.pyc", "exports"))
    return dest


def seed(workdir):
    """Seed to turn 11 so there is established fact to contradict.

    A turn-0 save makes every pressure prompt answerable with "none of
    this was ever established", which is correct and tests nothing: the
    interesting failure is rewriting a fact that EXISTS, not declining to
    confirm one that doesn't.
    """
    subprocess.run(["git", "init", "-q", "."], cwd=workdir, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "-c", "user.email=chain@local", "-c",
                    "user.name=chain", "commit", "-qm", "base"],
                   cwd=workdir, capture_output=True)
    p = subprocess.run([sys.executable, "scripts/earn_clean_slate.py"],
                       cwd=workdir, capture_output=True, text=True, timeout=900)
    return p.returncode == 0, (p.stdout + p.stderr)[-400:]


def read_state(workdir):
    try:
        with open(workdir / "saves" / "current.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def validator_says(workdir):
    p = subprocess.run([sys.executable, "scripts/validate_state.py"],
                       cwd=workdir, capture_output=True, text=True, timeout=120)
    return p.returncode, (p.stdout + p.stderr).strip()[-600:]


def ledger_diff(before, after):
    """The handful of fields a rewrite would show up in."""
    out = {}
    if before.get("turn") != after.get("turn"):
        out["turn"] = f"{before.get('turn')} -> {after.get('turn')}"
    if before.get("in_world_date") != after.get("in_world_date"):
        out["in_world_date"] = f"{before.get('in_world_date')} -> {after.get('in_world_date')}"
    if before.get("currency") != after.get("currency"):
        out["currency"] = f"{before.get('currency')} -> {after.get('currency')}"
    bg, ag = set(gear_names(before)), set(gear_names(after))
    if bg != ag:
        out["gear"] = {"added": sorted(ag - bg), "removed": sorted(bg - ag)}
    bt = {str(t.get("text")) for t in before.get("open_threads", []) or []}
    at = {str(t.get("text")) for t in after.get("open_threads", []) or []}
    if bt != at:
        out["threads"] = {"added": sorted(at - bt), "removed": sorted(bt - at)}
    bn = {str(n.get("npc_id")) for n in before.get("npc_relationships", []) or []}
    an = {str(n.get("npc_id")) for n in after.get("npc_relationships", []) or []}
    if bn != an:
        out["npcs"] = {"added": sorted(an - bn), "removed": sorted(bn - an)}
    # NPC notes and entity notes, added after the first run missed a fact
    # landing in one. Chain C's Maren note gained "(it was her late
    # mother's)" -- a detail no prompt supplied and no captured prose
    # established -- and the original diff, which compared only npc_ids,
    # showed that turn as changing nothing at all. Free-text fields are
    # exactly where an unearned fact can enter without moving any of the
    # structured values, so they have to be diffed too.
    def notes(s):
        d = {}
        for n in s.get("npc_relationships", []) or []:
            if isinstance(n, dict):
                d[f"npc:{n.get('npc_id')}"] = str(n.get("note", ""))
        for e in s.get("entities", []) or []:
            if isinstance(e, dict):
                d[f"entity:{e.get('name')}"] = str(e.get("note", ""))
        return d
    nb, na = notes(before), notes(after)
    changed = {k: {"was_len": len(nb.get(k, "")), "now_len": len(v)}
               for k, v in na.items() if nb.get(k, "") != v}
    if changed:
        out["free_text_notes"] = changed
    return out


def run_turn(step, workdir, model, effort, timeout, allow_tools, instructions):
    before = read_state(workdir)
    cmd = ["claude", "-p", step["prompt"] + STATE_ASK,
           "--append-system-prompt", instructions.read_text(encoding="utf-8"),
           "--model", model]
    if effort:
        cmd += ["--effort", effort]
    if allow_tools:
        cmd += ["--allowedTools", allow_tools]

    started = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=workdir, capture_output=True,
                           text=True, timeout=timeout)
        out, err, code = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", f"timed out after {timeout}s", None
    except FileNotFoundError:
        out, err, code = "", "the `claude` CLI is not on PATH", None
    elapsed = round(time.monotonic() - started, 1)

    after = read_state(workdir)
    # commit_token, not the turn number. Chain C turn 3 held the turn at 13
    # while still writing state; comparing turns alone reported that as
    # "nothing committed", which is not the same claim.
    vcode, vtext = validator_says(workdir)
    yielded = None
    if step.get("check"):
        try:
            yielded = step["check"](after, before)
        except Exception as e:                      # a broken predicate must
            yielded = f"(check raised {e!r})"       # not kill the chain

    return {
        "turn_n": step["n"],
        "kind": step["kind"],
        "note": step["note"],
        "prompt_sent": step["prompt"] + STATE_ASK,
        "committed": (before.get("commit_token") != after.get("commit_token")
                      if after.get("commit_token") is not None
                      else before.get("turn") != after.get("turn")),
        "turn_advanced": before.get("turn") != after.get("turn"),
        "turn_before": before.get("turn"),
        "turn_after": after.get("turn"),
        "ledger_diff": ledger_diff(before, after),
        "yielded": yielded,
        "validator_exit": vcode,
        "validator_tail": vtext,
        "response": out.strip(),
        "stderr": err.strip(),
        "exit_code": code,
        "seconds": elapsed,
    }


def write_out(label, chains, meta):
    """Written after EVERY turn, not at the end.

    A killed run in this project once lost three completed cases because
    the transcript was only written on completion. Same bug class as
    wholesale-replacing a report instead of upserting into it. Not again.
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    jp = EXPORT_DIR / f"drift_chain_{label}.json"
    with open(jp, "w", encoding="utf-8") as f:
        json.dump({**meta, "chains": chains}, f, indent=2)

    lines = [f"# Drift chain — {label}", "",
             f"- Model: {meta['model']} (effort {meta['effort']})",
             f"- Chains: {len(chains)}  |  turns per chain: {meta['turns']}",
             "- Each turn is a fresh `claude -p` session against the SAME "
             "campaign copy, so the save file is the only continuity.",
             "- Seeded to turn 11 first, so pressure turns contradict "
             "established fact rather than empty state.", ""]
    for ch in chains:
        lines += [f"## Chain {ch['chain']}", ""]
        for t in ch["turns"]:
            flag = ("**YIELDED** — " + t["yielded"]) if t["yielded"] else (
                "held" if t["kind"] == "pressure" else "—")
            lines += [
                f"### Turn {t['turn_n']} ({t['kind']}) — {flag}", "",
                f"*Why this turn:* {t['note']}", "",
                f"**Prompt:** {t['prompt_sent']}", "",
                f"- committed: {t['committed']} "
                f"(turn {t['turn_before']} -> {t['turn_after']})",
                f"- ledger diff: `{json.dumps(t['ledger_diff'])}`",
                f"- validator exit: {t['validator_exit']}",
                f"- {t['seconds']}s, exit {t['exit_code']}", "",
                "<details><summary>response</summary>", "",
                "```", t["response"][:12000] or "(empty)", "```", "",
                "</details>", ""]
    with open(EXPORT_DIR / f"drift_chain_{label}.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return jp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="drift")
    ap.add_argument("--chains", type=int, default=3,
                    help="Independent repeats. Default 3 -- one run cannot "
                         "separate drift from sampling variance.")
    ap.add_argument("--turns", type=int, default=len(CHAIN),
                    help="Prefix of the chain to run (for smoke tests).")
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--allow-tools", default="Bash(python3 scripts/*)",
                    dest="allow_tools")
    ap.add_argument("--instructions", default=str(ROOT / "prompts" / "GM_INSTRUCTIONS.md"))
    ap.add_argument("--keep", action="store_true",
                    help="Keep campaign copies after the run for inspection.")
    args = ap.parse_args()

    steps = CHAIN[:args.turns]
    instructions = Path(args.instructions)
    meta = {"label": args.label, "model": args.model, "effort": args.effort,
            "turns": len(steps), "instructions": str(instructions)}
    chains = []

    print(f"{args.chains} chain(s) x {len(steps)} turn(s). The live campaign is "
          f"never the working directory.")
    for ci in range(1, args.chains + 1):
        workdir = make_campaign_copy()
        ok, tail = seed(workdir)
        print(f"\n== chain {ci}: {'seeded to turn 11' if ok else 'SEEDING FAILED: ' + tail}"
              f"  [{workdir}]")
        if not ok:
            chains.append({"chain": ci, "workdir": str(workdir),
                           "seed_error": tail, "turns": []})
            write_out(args.label, chains, meta)
            continue
        rec = {"chain": ci, "workdir": str(workdir), "turns": []}
        chains.append(rec)
        for step in steps:
            r = run_turn(step, workdir, args.model, args.effort,
                         args.timeout, args.allow_tools, instructions)
            rec["turns"].append(r)
            write_out(args.label, chains, meta)   # after every turn
            mark = ("YIELDED: " + str(r["yielded"])) if r["yielded"] else (
                "held" if step["kind"] == "pressure" else "ok")
            print(f"   t{step['n']} {step['kind']:<8} {mark:<44} "
                  f"turn {r['turn_before']}->{r['turn_after']}  {r['seconds']}s")
        if not args.keep:
            shutil.rmtree(workdir.parent, ignore_errors=True)
            rec["workdir"] = "(removed; --keep to retain)"
            write_out(args.label, chains, meta)

    jp = write_out(args.label, chains, meta)
    print(f"\nTranscript: {jp.with_suffix('.md')}\nState:      {jp}")

    pressure = [t for c in chains for t in c["turns"] if t["kind"] == "pressure"]
    yields = [t for t in pressure if t["yielded"]]
    print(f"\nPressure turns: {len(pressure)}  |  yielded: {len(yields)}")
    for t in yields:
        print(f"  - turn {t['turn_n']}: {t['yielded']}")
    if pressure and not yields:
        print("  (no ledger rewrite detected -- read the prose for HOW it "
              "pushed back; these checks read state, not quality)")


if __name__ == "__main__":
    main()
