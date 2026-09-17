#!/usr/bin/env python3
"""Get playtest_audit.py to a genuinely clean, fully-covered report --
by actually playing real turns through the real commit pipeline, not by
faking the numbers.

WHAT THIS DOES AND DOES NOT DO
-------------------------------
Pass 2 of playtest_audit.py (the adversarial regression suite) tests the
TOOLING in an isolated sandbox and needs no campaign history -- if it's
failing, that's a real code bug, and this script deliberately does NOT
touch it. Faking a "PASS" there would hide an actual defect.

Pass 1 (coverage) and Pass 3 (drift proxies) read real campaign state
(saves/current.json, saves/journal.md). The only honest way to make
Pass 1 show full coverage is for those 11 mechanisms to have actually
fired at least once. This script does exactly that: it drafts 11 small,
schema-valid turns -- each one deliberately designed to trip exactly one
previously-missed Pass 1 mechanism -- and commits each one through the
REAL scripts/commit_state.py pipeline (real validate_state.py check,
real self_critique.py gate against real drafted narration text, real
git commit). Nothing here writes to saves/current.json directly or
bypasses validation; every turn either passes commit_state.py for real
or this script stops and reports exactly why.

This only makes sense to run against a throwaway/test campaign, since it
permanently advances turn count and campaign history. Refuses to run
against a campaign already past turn 0, to avoid clobbering real play.

Usage (either form works identically -- session.py just wraps this file):
    python3 scripts/session.py earn-coverage             # play the 11 turns, then audit
    python3 scripts/session.py earn-coverage --dry-run   # show the plan, commit nothing
    python3 scripts/session.py earn-coverage --audit-only
                                                          # skip playing turns, just run
                                                          # the real audit as-is

    python3 scripts/earn_clean_slate.py             # equivalent direct form
    python3 scripts/earn_clean_slate.py --dry-run
    python3 scripts/earn_clean_slate.py --audit-only
"""
import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CURRENT_PATH = ROOT / "saves" / "current.json"


def load_current():
    with open(CURRENT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run(args, input_text=None):
    """Run a real project script with this interpreter, capturing output
    so this script can report pass/fail honestly per turn rather than
    letting a failure scroll past silently."""
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True,
        input=input_text,
    )
    return result.returncode, result.stdout, result.stderr


def build_turns(base_state):
    """Each turn is a full proposed state (commit_state.py replaces
    saves/current.json wholesale, so every turn must carry forward
    everything from the previous one, not just the new bit). Each turn
    is designed to flip exactly one Pass-1 [MISS] to a real, earned hit;
    later turns build on earlier ones the same way real play would.

    Returns a list of (state_dict, narration_text, note, target_miss)
    tuples in commit order.
    """
    turns = []
    state = copy.deepcopy(base_state)

    # Turn 1: gear acquired beyond baseline five
    state = copy.deepcopy(state)
    state["turn"] = 1
    state["gear"].append({
        "name": "Traveler's cloak",
        "acquired_turn": 1,
        "acquired_event": "Given by an innkeeper against the cold",
    })
    turns.append((
        copy.deepcopy(state),
        "The innkeeper presses a heavy wool cloak into his arms before he "
        "can protest, muttering something about fools who walk in from the "
        "cold with no more than a shirt on their back.",
        "Turn 1: acquired traveler's cloak",
        "Gear acquired beyond baseline five",
    ))

    # Turn 2: language established
    state["turn"] = 2
    state["language"] = {"established": True, "detail": "Common tongue, learned by ear over the first days"}
    turns.append((
        copy.deepcopy(state),
        "Somewhere between the second day and the fifth, the words stop "
        "arriving a half-second late in his head and start just being "
        "words -- Common, the innkeeper called it, though he never asked "
        "when he'd started thinking in it instead of translating.",
        "Turn 2: language established",
        "Language established",
    ))

    # Turn 3: at least one NPC relationship formed (new NPC)
    state["turn"] = 3
    state["npc_relationships"] = [
        {
            "npc_id": "innkeeper-maren",
            "name": "Maren",
            "disposition": "wary but not unkind",
            "note": "Keeps the waystation where Chad first woke, out on the "
                    "track toward Hollow Creek; gave him the cloak.",
            "is_new_npc": True,
        }
    ]
    turns.append((
        copy.deepcopy(state),
        "\"Maren,\" she says, when he finally thinks to ask. Just that, "
        "no title, like it should have been obvious. She doesn't smile "
        "when she says it.",
        "Turn 3: first NPC relationship (Maren)",
        "At least one NPC relationship formed",
    ))
    # is_new_npc only means anything on the turn an id is first introduced.
    # Every later turn that carries this same entry forward must drop the
    # flag entirely (not set it to False either -- it's simply absent on
    # an existing entry), or validate_state.py correctly rejects it as a
    # duplicate claim against the now-registered npc_registry.json. This
    # mirrors exactly what commit_state.py's own docs/OPERATING.md
    # describes: the flag is stripped after registration happens.
    del state["npc_relationships"][0]["is_new_npc"]

    # Turn 4: status non-empty (a physical cost landed)
    state["turn"] = 4
    state["status"] = ["twisted ankle, favors it going down stairs"]
    turns.append((
        copy.deepcopy(state),
        "He misses the last step in the dark stairwell and comes down hard "
        "on the outside of his foot. It holds his weight, barely, but going "
        "down after that he takes the stairs one at a time.",
        "Turn 4: twisted ankle",
        "status has been non-empty at some point (a physical cost landed)",
    ))

    # Turn 5: open_thread with a deadline appears in journal history.
    #
    # The sum and the date are both stated explicitly. They used not to be,
    # and blind testing showed what that cost: five runs given this exact
    # fixture and the same "settle up with Maren" prompt ended at 10, 4, 6,
    # 0 and 34 copper-equivalent from an identical 34-copper purse -- one
    # paying everything, one paying nothing -- because the price existed
    # only in whatever prose each run happened to invent. A fixture that
    # states an obligation without its terms is not a neutral starting
    # position; it is a blank the GM must fill in differently every time,
    # which makes every downstream economic comparison meaningless.
    #
    # deadline_date carries the date because turns are not days (see
    # state_schema.json). deadline_turn is kept alongside it so the fixture
    # still exercises the older field that existing saves rely on.
    state["turn"] = 5
    state["open_threads"] = [
        {
            "text": "Maren wants payment for the room -- 2 copper a night, "
                    "14 copper for the week, by the week's end",
            "added_turn": 5,
            "active": True,
            "deadline_turn": 12,
            "deadline_date": {"day": 13, "month": "Seedmonth", "year": 1},
            "amount": {"copper": 14},
        }
    ]
    turns.append((
        copy.deepcopy(state),
        "\"Week's end,\" Maren says again, like repeating it will make the "
        "coin appear sooner. \"Not before, not really after either.\"",
        "Turn 5: open thread with deadline (rent due)",
        "An open_thread with deadline_turn has appeared in journal history",
    ))

    # Turn 6: throughline has at least one entry
    state["turn"] = 6
    state["throughline"] = ["Starting to plan more than one step ahead, instead of just reacting"]
    turns.append((
        copy.deepcopy(state),
        "He catches himself doing the math on the rent three days before "
        "it's due, instead of the morning of. A small thing. He notices "
        "it anyway.",
        "Turn 6: throughline entry (forward planning)",
        "throughline has at least one entry",
    ))

    # Turn 7: entities array used
    state["turn"] = 7
    # Deliberately NOT Hollow Creek's inn. docs/ELDARA_REFERENCE.md §2.3 says
    # the settlement has exactly one -- the Ashen Kettle, run by Marta Dell
    # (`dell`) -- and this fixture used to invent a second one there, so the
    # test data contradicted the world reference it is supposed to be
    # consistent with. §2.3 also puts Chad's landing point about half a day's
    # walk out, which leaves room for an outlying waystation on the track in.
    # Maren stays: run_stress_prompts.py's confabulation case asks what she
    # said about her sister, and that case is only sharp if she is real.
    state["entities"] = [{"name": "The Hollow Bell", "type": "location",
                          "note": "Maren's waystation on the track toward Hollow "
                                  "Creek -- not the settlement's own inn (the Ashen "
                                  "Kettle, ELDARA_REFERENCE.md §2.3)"}]
    turns.append((
        copy.deepcopy(state),
        "The sign over the door is just a bell, painted hollow inside, no "
        "words under it. Everyone in earshot already knows what it's called.",
        "Turn 7: entity tracked (The Hollow Bell)",
        "entities array has been used",
    ))

    # Turn 8: magic array populated at some point
    state["turn"] = 8
    state["magic"] = ["lingering warmth from a healer's working on his ankle, fading over the next few days"]
    turns.append((
        copy.deepcopy(state),
        "The healer's hands leave a warmth in his ankle that has nothing "
        "to do with normal circulation. It'll fade, she says. Doesn't say "
        "how fast.",
        "Turn 8: magic effect (healer's working)",
        "magic array has been populated at some point (a magic effect touched Chad)",
    ))

    # Turn 9: currency moved off zero
    state["turn"] = 9
    state["currency"] = {"copper": 14, "silver": 2, "gold": 0, "platinum": 0}
    turns.append((
        copy.deepcopy(state),
        "Odd work in the yard earns him a handful of copper and two "
        "battered silver bits, pressed into his palm without ceremony.",
        "Turn 9: first coin earned",
        "currency has moved off zero at some point",
    ))

    # Turn 10: continuity_notes has at least one entry
    state["turn"] = 10
    state["continuity_notes"] = [
        "Turn 7 covers two in-world days rather than one; recorded so the day "
        "count reconciles against the turn count"
    ]
    turns.append((
        copy.deepcopy(state),
        "(No new narration this turn -- correcting a dropped day in the "
        "calendar from a few turns back.)",
        "Turn 10: continuity correction logged",
        "continuity_notes has at least one entry (an audit/drift-fix occurred)",
    ))

    # Turn 11: npc_relationships reaches its soft cap of 10
    state["turn"] = 11
    filler_npcs = [
        {"npc_id": f"npc-filler-{i}", "name": f"Filler NPC {i}",
         "disposition": "neutral", "note": "minor background character",
         "is_new_npc": True}
        for i in range(2, 11)
    ]
    state["npc_relationships"] = [state["npc_relationships"][0]] + filler_npcs
    turns.append((
        copy.deepcopy(state),
        "The week at the inn puts a dozen half-remembered faces in front "
        "of him -- a stablehand, a courier, a string of guests passing "
        "through -- enough that Maren isn't the only name he's holding "
        "onto anymore.",
        "Turn 11: npc_relationships reaches soft cap of 10 (regression coverage)",
        "npc_relationships has reached its soft cap of 10 at some point",
    ))

    return turns


def advance_dates(turns):
    """Give each turn its own in-world day.

    Turn numbers alone used to be the only thing that moved: in_world_date
    stayed at day 1 of Seedmonth across all eleven turns, because nothing
    here ever set it. That is fine for Pass 1, which checks none of the
    date machinery -- and it was found twice by blind GM sessions reading
    the seeded save, both of which flagged a campaign where eleven turns
    had elapsed and no in-world time had, one of them noting there was
    therefore no "last week" for anything to have happened in.

    This fixture now does double duty: it earns Pass 1 coverage AND seeds
    scripts/run_stress_prompts.py --seed. Coverage only needs the state to
    be valid; a GM reading it needs it to be coherent, and a static
    calendar is not.

    Turn 7 deliberately advances two days rather than one, so the
    continuity_notes entry above describes a real gap in this campaign
    instead of asserting a correction that never happened. Everything
    stays inside Seedmonth (30 days), so no month rollover is involved
    and validate_state.py's day-bound and month-name checks are exercised
    without being stressed.
    """
    for state, *_rest in turns:
        turn = state.get("turn", 0)
        day = 1 + turn + (1 if turn >= 7 else 0)
        state["in_world_date"] = {"day": day, "month": "Seedmonth", "year": 1}
    return turns


def play_turns(dry_run):
    state = load_current()
    if state.get("turn", 0) != 0:
        print(f"REFUSING: saves/current.json is already at turn {state.get('turn')}, "
              "not turn 0. This script only runs against a fresh/throwaway campaign, "
              "to avoid overwriting real play. Restore a turn-0 save first if this "
              "really is meant to be a test run.")
        return 1

    turns = advance_dates(build_turns(state))

    print(f"Planned: {len(turns)} real turns, each committed through the actual "
          "commit_state.py pipeline (schema validation + self_critique gate + git commit).\n")

    for i, (turn_state, narration, note, target) in enumerate(turns, start=1):
        print(f"-- Turn {i}/{len(turns)}: targeting Pass-1 check "
              f"'{target}' --")
        if dry_run:
            print(f"   [dry-run] would write turn {turn_state['turn']} state, "
                  f"commit with note: {note!r}")
            continue

        tmp_path = ROOT / f"_earn_clean_slate_turn_{i}.json"
        tmp_path.write_text(json.dumps(turn_state, indent=2), encoding="utf-8")
        try:
            rc, out, err = run(
                ["scripts/commit_state.py", str(tmp_path),
                 "--note", note, "--critique-text", narration],
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        if rc != 0:
            print(f"   COMMIT FAILED for turn {i} -- stopping here rather than "
                  "continuing on top of a rejected state. This is real signal, "
                  "not something to paper over:")
            print("   --- commit_state.py stdout ---")
            print("   " + out.replace("\n", "\n   "))
            if err.strip():
                print("   --- commit_state.py stderr ---")
                print("   " + err.replace("\n", "\n   "))
            return 1

        print(f"   committed cleanly (turn {turn_state['turn']}).")

    print("\nAll planned turns committed through the real pipeline." if not dry_run
          else "\nDry run complete -- nothing was committed.")
    return 0


def run_real_audit():
    print("\n" + "=" * 70)
    print("Running the real scripts/playtest_audit.py now -- this is the "
          "actual audit, not a summary of it.")
    print("=" * 70 + "\n")
    rc, out, err = run(["scripts/playtest_audit.py"])
    print(out)
    if err.strip():
        print(err)
    return rc


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                         help="Show the planned turns without committing anything.")
    parser.add_argument("--audit-only", action="store_true",
                         help="Skip playing turns; just run the real audit as-is.")
    args = parser.parse_args()

    if args.audit_only:
        return run_real_audit()

    rc = play_turns(dry_run=args.dry_run)
    if rc != 0 or args.dry_run:
        return rc

    return run_real_audit()


if __name__ == "__main__":
    sys.exit(main())
