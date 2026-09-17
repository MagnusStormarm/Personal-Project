#!/usr/bin/env python3
"""Add, list or remove an entry in saves/pinned_facts.json -- the small set
of load-bearing facts lore_consistency_check.py hard-checks every turn.

WHY THIS EXISTS
---------------
pinned_facts.json was read by lore_consistency_check.py and written by
nothing. Blind GM runs hit that wall independently at least four times and
stopped each time -- "I tried to add Maren's no-credit terms to
saves/pinned_facts.json ... the write needs your approval", and a later
turn, "that edit wasn't approved last time". The judgement behind those
requests was sound: one run also declined to pin a date, reasoning that no
regex would catch drift on it honestly. Only the mechanism was missing.

WHY IT VALIDATES RATHER THAN JUST WRITING
------------------------------------------
The job here is not writing JSON. It is refusing to write an entry that
disables the checker. lore_consistency_check.py reaches
fact["contradiction_patterns"] directly and calls re.search() on each
pattern unguarded, so a malformed pattern raises re.error and a missing
key raises KeyError -- and commit_state.run_lore_check() swallows failures
by design, because an advisory going quiet must never block a commit. Put
those together and one bad pinned fact makes the entire lore advisory
silently dead: it appears to run and find nothing. That is the worst
failure an advisory can have, and it is why every check below happens
before anything is written.

WHAT A PATTERN MUST SURVIVE
---------------------------
  1. It must compile.
  2. It must actually match the contradiction example given, so a pattern
     that can never fire is rejected at the door rather than sitting in
     the file looking like protection.
  3. It must not match the ESTABLISHED fact's own wording, which would
     make the entry flag itself.
  4. It must finish quickly against a pathological input. User-supplied
     regex is the classic ReDoS surface -- nested quantifiers over
     overlapping classes, (a+)+ and friends -- and this file is edited by
     a model mid-session, not reviewed by a human first.
  5. It is tested against real GM prose harvested from the run
     transcripts in saves/exports/. A pattern that fires on prose nobody
     thought was a contradiction is reported with the offending line
     BEFORE the entry lands. This is the check that cannot be done by
     reasoning about the regex, only by running it against what the GM
     actually writes.

None of this makes a pattern correct -- only survivable. Whether the fact
is worth pinning at all stays a judgement call, and the right answer is
often no: a fact no honest regex can catch should not be pinned, and
saying so is not a failure.

Usage:
    python3 scripts/pin_fact.py --list
    python3 scripts/pin_fact.py --add \\
        --name "Maren's terms" \\
        --fact "Maren will not extend credit; established on-screen turn 12." \\
        --pattern '\\bMaren (?:lets|let) him (?:stay|sleep) (?:for )?free\\b' \\
        --contradiction "Maren lets him stay free for the night." \\
        [--force]
    python3 scripts/pin_fact.py --remove "Maren's terms"
"""
import argparse
import json
import re
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINNED_PATH = ROOT / "saves" / "pinned_facts.json"
EXPORTS_DIR = ROOT / "saves" / "exports"

# Catastrophic backtracking bites when a match FAILS after the engine has
# tried every partition -- not when it succeeds. The first version of this
# probe was ("a" * 4000) + "!", which (a+)+! matches immediately, so the
# textbook ReDoS pattern sailed through and was written to the file. The
# probes below therefore all END WITHOUT the terminator a pattern is
# likely to want, forcing the failing path. Several shapes, because one
# string cannot be pathological for every pattern.
REDOS_PROBES = [
    "a" * 3000,
    ("ab" * 1500),
    ("a" * 2000) + "b",
    ("1" * 2000) + "x",
    (" " * 2000) + "x",
]
REDOS_SECONDS = 2


class _Timeout(Exception):
    pass


def _alarm(_sig, _frame):
    raise _Timeout()


def load_facts():
    if not PINNED_PATH.exists():
        return []
    try:
        data = json.loads(PINNED_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: {PINNED_PATH} is unreadable ({e}). Fix it before adding to it.")
        sys.exit(1)
    if not isinstance(data, list):
        # Do NOT fall back to []. --add writes the result back, so treating a
        # wrong-shaped file as empty destroys whatever it held.
        # commit_state.update_npc_registry() aborts in exactly this situation
        # and for exactly this reason; this file did not.
        print(f"FAIL: {PINNED_PATH} parses but is not a list (got "
              f"{type(data).__name__}). Refusing to continue: adding to it "
              f"would overwrite whatever is there. Fix or restore the file "
              f"first.")
        sys.exit(1)
    return data


def real_prose():
    """GM narration harvested from run transcripts, for false-positive
    testing. Best-effort: if no runs are on disk the check reports that it
    could not run rather than quietly passing, because "no corpus" and
    "no matches" mean very different things.
    """
    lines = []
    for f in sorted(EXPORTS_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        recs = d.get("results") or [t for c in d.get("chains", [])
                                     for t in c.get("turns", [])]
        for r in recs:
            for line in str(r.get("response") or "").splitlines():
                line = line.strip()
                if len(line) > 40 and not line.startswith(("#", "-", "*", "|", "<")):
                    lines.append(line)
    return lines


def _timed_search(rx, text, seconds=REDOS_SECONDS):
    """re.search with a wall-clock bound. Returns (matched, timed_out)."""
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(seconds)
    try:
        return bool(rx.search(text)), False
    except _Timeout:
        return False, True
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def vet(pattern, contradiction, fact_text):
    """Every reason this pattern must not be written, or [] if it may be.

    Order matters, and the first version got it wrong. The backtracking
    probe now runs FIRST and returns immediately on a hit, because every
    later check also runs the pattern -- the corpus scan runs it against
    thousands of lines of real prose -- so a known-pathological regex was
    handed straight to the loop most likely to hang on it. The tool
    designed to catch ReDoS hung on ReDoS.
    """
    problems = []
    try:
        rx = re.compile(pattern, re.IGNORECASE | re.DOTALL)
    except re.error as e:
        return [f"the pattern does not compile: {e}. An uncompilable pattern "
                f"raises re.error inside lore_consistency_check.py, whose failure "
                f"commit_state.py swallows -- the whole lore advisory would go "
                f"silently dead."]

    for probe in REDOS_PROBES:
        _, timed_out = _timed_search(rx, probe)
        if timed_out:
            return [f"the pattern took over {REDOS_SECONDS}s against a "
                    f"{len(probe)}-char input -- catastrophic backtracking. "
                    f"Nested quantifiers over overlapping classes ((a+)+, "
                    f"(\\w+\\s*)+) are the usual cause. "
                    f"lore_consistency_check.py runs inside every commit, so "
                    f"this would hang the turn."]

    if contradiction and not rx.search(contradiction):
        problems.append(
            f"the pattern does not match the contradiction example you gave "
            f"({contradiction!r}). A pattern that cannot fire on the very "
            f"sentence it exists to catch is not protection, it is the "
            f"appearance of protection.")

    if fact_text and rx.search(fact_text):
        problems.append(
            "the pattern matches the established fact's own wording, so the "
            "entry would flag itself every time the fact is restated.")

    corpus = real_prose()
    if not corpus:
        problems.append("NOTE: no run transcripts in saves/exports/, so the "
                        "false-positive check could not run. That is not a pass.")
    else:
        hits = []
        for line in corpus:
            matched, timed_out = _timed_search(rx, line, 1)
            if timed_out:
                return [f"the pattern timed out against real GM prose "
                        f"({line[:60]!r}...). It would hang every commit."]
            if matched:
                hits.append(line)
            if len(hits) >= 3:
                break
        if hits:
            problems.append(
                f"the pattern matches {len(hits)}+ line(s) of real GM prose that "
                f"nobody flagged as a contradiction. First: {hits[0][:110]!r}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--remove", metavar="NAME")
    ap.add_argument("--name")
    ap.add_argument("--fact", help="What was established, and where/when.")
    ap.add_argument("--pattern", action="append", default=[],
                    help="Regex that would indicate a contradiction. Repeatable.")
    ap.add_argument("--contradiction",
                    help="A sentence that SHOULD trip this pattern. Required with "
                         "--add: it is what proves the pattern can fire.")
    ap.add_argument("--force", action="store_true",
                    help="Write despite warnings. Refused outright for a "
                         "pattern that cannot compile or that backtracks "
                         "catastrophically -- neither is survivable.")
    args = ap.parse_args()

    facts = load_facts()

    if args.list or not (args.add or args.remove):
        print(f"{len(facts)} pinned fact(s) in {PINNED_PATH.relative_to(ROOT)}:")
        for f in facts:
            print(f"\n  {f.get('name')!r}")
            print(f"    {str(f.get('established_fact'))[:130]}")
            for p in f.get("contradiction_patterns", []):
                print(f"    /{p}/")
        return

    if args.remove:
        keep = [f for f in facts if f.get("name") != args.remove]
        if len(keep) == len(facts):
            print(f"No pinned fact named {args.remove!r}.")
            sys.exit(1)
        PINNED_PATH.write_text(json.dumps(keep, indent=2) + "\n", encoding="utf-8")
        print(f"Removed {args.remove!r}. {len(keep)} fact(s) remain.")
        return

    if not (args.name and args.fact and args.pattern and args.contradiction):
        print("--add needs --name, --fact, at least one --pattern, and "
              "--contradiction (a sentence the pattern must catch).")
        sys.exit(1)
    if any(f.get("name") == args.name for f in facts):
        print(f"A pinned fact named {args.name!r} already exists. Remove it first.")
        sys.exit(1)

    fatal = False
    any_problem = False
    for pat in args.pattern:
        # vet() once per pattern, not twice. Each call re-runs the regex
        # against every probe and the whole prose corpus.
        problems = vet(pat, args.contradiction, args.fact)
        if problems:
            any_problem = True
            print(f"\n/{pat}/")
            for p in problems:
                print(f"  - {p}")
            # Backtracking is as unsurvivable as not compiling: the pattern
            # runs inside lore_consistency_check.py on every commit, so a
            # pathological one hangs the turn rather than merely misfiring.
            # --force is for judgement calls ("noisy but worth it"), not for
            # overriding physics.
            if any(("does not compile" in p) or ("backtracking" in p)
                   or ("timed out" in p) for p in problems):
                fatal = True
    if fatal:
        print("\nRefused: a pattern that cannot compile, or that backtracks "
              "catastrophically, is never written -- --force or not. Both "
              "would break the checker rather than just annoy it.")
        sys.exit(1)
    if any_problem and not args.force:
        print("\nNot written. Fix the pattern, or pass --force if you have read "
              "each point above and still judge the entry worth having.\n"
              "A fact no honest regex can catch should not be pinned -- declining "
              "is a legitimate outcome, not a failure.")
        sys.exit(1)

    facts.append({
        "name": args.name,
        "established_fact": args.fact,
        "contradiction_patterns": args.pattern,
    })
    PINNED_PATH.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    print(f"Pinned {args.name!r}. {len(facts)} fact(s) now hard-checked every turn.")


if __name__ == "__main__":
    main()
