#!/usr/bin/env python3
"""Suggest which entry in npc_relationships or open_threads is the safest
candidate to prune when a soft cap is about to be exceeded. This ranks
candidates; it does not decide -- the final call is always a narrative
judgment. Its ranking heuristic is naive (see caveats below) -- always
confirm or override the top suggestion rather than trusting it blindly.

Ranking heuristics:
  - npc_relationships: when last_referenced_turn is available (stamped by
    commit_state.py whenever an NPC's name is matched in a turn's
    narration -- see stamp_npc_recency() there), rank by actual turns
    since last mention -- a real, checkable staleness signal instead of
    a guess. Falls back to the older note/disposition-length heuristic
    for any entry without that field yet (older saves, or a name never
    yet matched verbatim). CAVEAT on the fallback path only: it can rank
    a narratively important but recently-thin-on-detail NPC (e.g. an
    authority figure introduced but not yet elaborated) as "safe to
    prune" when they're actually not -- thinness of recorded detail is
    not the same as narrative importance. The recency-based path doesn't
    share this specific flaw, but has its own: an NPC referred to only
    by title, pronoun, or a prior display name won't be matched by
    stamp_npc_recency()'s whole-word name check, so their entry can look
    stale even while narratively active.
  - open_threads: prefer pruning entries with no deadline_turn and the
    lowest added_turn (oldest, least urgent, most likely to have quietly
    stopped mattering).

Usage:
    python3 scripts/prune_advisor.py npc_relationships
    python3 scripts/prune_advisor.py open_threads
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT_PATH = ROOT / "saves" / "current.json"


def load_state():
    with open(CURRENT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_bearing_reasons(npc, state):
    """Everywhere else in the save this NPC is anchored.

    Staleness says when someone was last mentioned in narration. It says
    nothing about whether the rest of the state leans on them, and those
    come apart: the NPC that blind testing found at the top of the prune
    list held the only open thread, the only entity, and the provenance
    of the only non-baseline gear Chad owned. None of that is visible to
    a recency number.

    Matched on the NPC's name AND on the words in their npc_id, because
    ids are descriptive slugs and the reference is often to the role
    rather than the name -- "innkeeper-maren" is anchored by a gear entry
    reading "Given by an innkeeper against the cold", which a name-only
    match misses entirely. Whole-word matching only, so "innkeeper" does
    not fire on "a roadside inn".

    Known false positive, accepted rather than engineered around: a name
    that is also an ordinary English word over-matches. An NPC called
    Will is reported as anchored by a thread reading "Find the will of
    the old lord". That is the safe direction for an annotation a human
    reads and dismisses in a second -- the expensive error here is the
    other one, silently failing to mark someone the rest of the save
    leans on, and then pruning them. This never blocks anything, so it
    can afford to be noisy in a way the commit gate cannot.
    """
    terms = set()
    name = str(npc.get("name") or "").strip().lower()
    if name:
        terms.add(name)
    for part in re.split(r"[-_\s]+", str(npc.get("npc_id") or "").lower()):
        if len(part) > 2:
            terms.add(part)
    if not terms:
        return []

    def mentions(text):
        blob = str(text or "").lower()
        return any(re.search(rf"\b{re.escape(t)}\b", blob) for t in terms)

    reasons = []
    for thread in state.get("open_threads", []) or []:
        if isinstance(thread, dict) and mentions(thread.get("text")):
            reasons.append(f'open thread "{thread.get("text")}"')
    for entity in state.get("entities", []) or []:
        if isinstance(entity, dict) and mentions(
                f"{entity.get('name','')} {entity.get('note','')}"):
            reasons.append(f'entity "{entity.get("name")}"')
    for gear in state.get("gear", []) or []:
        if isinstance(gear, dict) and mentions(gear.get("acquired_event")):
            reasons.append(f'gear "{gear.get("name")}" came from them')
    return reasons


# A gap below this is "recently mentioned" -- short enough that topping the
# staleness ranking says nothing useful about whether the entry is prunable.
RECENT_GAP = 3


def rank_npcs(npcs, current_turn=None):
    """Ranks prune candidates using last_referenced_turn when it's
    present (stamped by commit_state.py's stamp_npc_recency() whenever an
    NPC's name is matched in a turn's narration) -- an NPC not mentioned
    in a long time is a genuinely safer prune candidate than one just
    mentioned, which the old note/disposition-only heuristic had no way
    to express at all. Falls back to the original heuristic for any NPC
    missing the field (older saves predating this addition, or an NPC
    whose name has never yet been matched by stamp_npc_recency()'s
    whole-word check), so this is additive, not a hard requirement on
    every entry having the new field.

    Scoring convention: HIGHER score = safer to prune (list is sorted
    descending, safest-first).

    Entries WITH recency data and entries WITHOUT it are returned as two
    separate lists rather than one merged ranking, because there is no
    correct position on a shared number line for "I don't know".

    An earlier version put untracked entries on a range capped below
    every tracked score, reasoning that unknown staleness should never
    look safer than a measured one. That is true as stated and wrong in
    effect: it means a tracked entry mentioned THIS turn (gap 0) outranks
    every entry never mentioned at all, so the advisor's top pick becomes
    the most recently referenced NPC whenever recency data is sparse --
    which is the normal state early in a campaign, since
    stamp_npc_recency() only fires on a whole-word name match. Blind
    testing caught exactly that: against a seeded campaign the top
    recommendation was the one load-bearing NPC, ranked above nine
    interchangeable stubs.

    Flipping the offset would be worse. An NPC shows as untracked when
    their name has never matched narration, and awkwardly-named central
    characters are prime candidates for that -- calling them the safest
    prune is the original documented failure mode with more force.

    So neither direction is used. Tracked entries rank by measured
    staleness; untracked entries are handed back unranked, for a human to
    judge.

    Returns (tracked_ranked, untracked).
    """
    tracked, untracked = [], []
    for npc in npcs:
        if "last_referenced_turn" in npc and current_turn is not None:
            tracked.append(npc)
        else:
            untracked.append(npc)

    # Turns since last mention is the entire signal here: a real,
    # checkable staleness measure, highest gap (stalest) first.
    tracked.sort(key=lambda n: current_turn - n["last_referenced_turn"], reverse=True)
    return tracked, untracked


def rank_threads(threads):
    def score(thread):
        # Prefer pruning: no active deadline, then oldest added_turn.
        active_penalty = 100 if thread.get("active") else 0
        return active_penalty - thread.get("added_turn", 0)

    return sorted(threads, key=score)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("npc_relationships", "open_threads"):
        print("Usage: python3 scripts/prune_advisor.py npc_relationships|open_threads")
        sys.exit(1)

    field = sys.argv[1]
    if not CURRENT_PATH.exists():
        print(f"No state file found at {CURRENT_PATH}")
        sys.exit(1)

    try:
        state = load_state()
    except (json.JSONDecodeError, OSError, RecursionError) as e:
        print(f"FAIL: could not read/parse {CURRENT_PATH}: {e}")
        sys.exit(1)

    if not isinstance(state, dict):
        # Valid JSON that isn't an object at the top level (e.g. a bare
        # list) would otherwise crash on the first state.get() call below.
        print(f"FAIL: {CURRENT_PATH} parsed as valid JSON but is not an object "
              f"(got {type(state).__name__}, expected a dict).")
        sys.exit(1)

    items = state.get(field, [])

    if not items:
        print(f"{field} is empty -- nothing to prune.")
        return

    if field == "npc_relationships":
        current_turn = state.get("turn")
        tracked, untracked = rank_npcs(items, current_turn=current_turn)

        if tracked:
            print("Ranked by measured staleness (longest since last mention first):")
            for npc in tracked:
                gap = current_turn - npc["last_referenced_turn"]
                print(f"  - {npc.get('name')} ({npc.get('npc_id')}) — disposition: "
                      f"{npc.get('disposition', '(none)')!r}, last referenced turn "
                      f"{npc['last_referenced_turn']} ({gap} turns ago)")
                for reason in load_bearing_reasons(npc, state):
                    print(f"      LOAD-BEARING: {reason}")
            # Ordering these is not the same as any of them being safe. With
            # one tracked entry the "first" is also the last, and a list
            # headed "safest first" would present an NPC mentioned this turn
            # as the prune to make.
            stalest_gap = current_turn - tracked[0]["last_referenced_turn"]
            if stalest_gap < RECENT_GAP:
                print(f"\n  None of these is actually stale -- even the longest gap is "
                      f"{stalest_gap} turn(s).\n  Being top of this list does not make an "
                      "entry a safe prune; it only means\n  nothing tracked has gone "
                      "longer unmentioned.")
        else:
            print("No entry has recency data yet, so nothing can be ranked by staleness.")

        if untracked:
            print("\nNOT RANKABLE -- no recency data (predates recency tracking, or the")
            print("name has never matched narration). Deliberately left unordered: an")
            print("unmatched name is as often a central character as a forgettable one,")
            print("so neither end of the list would be honest. Judge these yourself:")
            for npc in sorted(untracked, key=lambda n: str(n.get("npc_id"))):
                print(f"  - {npc.get('name')} ({npc.get('npc_id')}) — disposition: "
                      f"{npc.get('disposition', '(none)')!r}")
                for reason in load_bearing_reasons(npc, state):
                    print(f"      LOAD-BEARING: {reason}")
    else:
        ranked = rank_threads(items)
        print("Ranked prune candidates (safest first):")
        for t in ranked:
            deadline = f", deadline_turn={t['deadline_turn']}" if t.get("deadline_turn") else ""
            print(f"  - \"{t.get('text')}\" (added_turn={t.get('added_turn')}, active={t.get('active', False)}{deadline})")

    if field == "npc_relationships":
        anchored = [n for n in items if isinstance(n, dict)
                    and load_bearing_reasons(n, state)]
        if anchored:
            print(f"\n{len(anchored)} entry(ies) marked LOAD-BEARING are referenced "
                  "elsewhere in the save.\nPruning one leaves those references pointing "
                  "at an NPC no longer in\nnpc_relationships. The registry still "
                  "remembers them, but the working set\nwill not.")

    print("\nThis is a ranked suggestion, not a decision -- confirm or override it.")
    print("The ranking is a naive heuristic (see this script's own docstring for its known")
    print("limitation); a narratively important NPC or thread can rank as 'safe' here.")


if __name__ == "__main__":
    main()
