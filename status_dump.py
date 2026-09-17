#!/usr/bin/env python3
"""Print the expanded status template (see prompts/STATUS_TEMPLATE.md)
directly from saves/current.json, so status requests are answered from
the actual file rather than the model's memory of the conversation.

Usage:
    python3 scripts/status_dump.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT_PATH = ROOT / "saves" / "current.json"


def main():
    if not CURRENT_PATH.exists():
        print(f"No state file found at {CURRENT_PATH}")
        return

    try:
        with open(CURRENT_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError, RecursionError) as e:
        # docs/RECOVERY.md's first recovery step for a corrupted
        # saves/current.json is to run this exact script to retrieve the
        # last known-good state -- so failing here needs to give a clear
        # message and a pointer to the next step, not a raw traceback,
        # since this is exactly the tool a person reaches for mid-crisis.
        print(f"FAIL: could not read/parse {CURRENT_PATH}: {e}")
        print("saves/current.json appears corrupted. See docs/RECOVERY.md's")
        print("'saves/current.json won't validate' section -- check")
        print("saves/backups/ for the most recent good snapshot.")
        return

    if not isinstance(state, dict):
        # Valid JSON that isn't an object at the top level (e.g. a bare
        # list) is a different failure mode than malformed JSON above,
        # but the same practical consequence -- this script needs to
        # stay usable exactly when RECOVERY.md needs it most.
        print(f"FAIL: {CURRENT_PATH} parsed as valid JSON but is not an object "
              f"(got {type(state).__name__}, expected a dict).")
        print("saves/current.json appears corrupted. See docs/RECOVERY.md's")
        print("'saves/current.json won't validate' section -- check")
        print("saves/backups/ for the most recent good snapshot.")
        return

    date = state.get("in_world_date", {})
    currency = state.get("currency", {})
    gear = state.get("gear", [])
    npcs = state.get("npc_relationships", [])
    threads = state.get("open_threads", [])
    throughline = state.get("throughline", [])
    language = state.get("language", {})
    status = state.get("status", [])

    print(f"Date: Day {date.get('day', '?')} of {date.get('month', '?')}, Year {date.get('year', '?')}")
    print(f"Location / Scene: {state.get('scene', '(unset)')}")
    current_location = state.get("current_location")
    if current_location:
        print(f"  Tracked location: {current_location} (see scripts/location_lookup.py)")
    travel = state.get("travel")
    if isinstance(travel, dict) and travel.get("destination"):
        eta = travel.get("eta_date") or {}
        eta_str = f" (ETA day {eta.get('day', '?')} of {eta.get('month', '?')})" if eta else ""
        print(f"  In transit to: {travel['destination']}{eta_str}")
    print("Gear:")
    if gear:
        for g in gear:
            cond = f" ({g['condition']})" if g.get("condition") else ""
            print(f"  - {g.get('name')}{cond}")
    else:
        print("  (none)")
    print(
        f"Currency: {currency.get('copper', 0)} copper / {currency.get('silver', 0)} silver / "
        f"{currency.get('gold', 0)} gold / {currency.get('platinum', 0)} platinum"
    )
    print(f"Status / Injuries: {', '.join(status) if status else '(none)'}")
    print(f"Language: {language.get('detail', '(not yet established)')}")
    print("Key NPCs / Relationships:")
    if npcs:
        for n in npcs:
            disp = f" — {n['disposition']}" if n.get("disposition") else ""
            print(f"  - {n.get('name')} ({n.get('npc_id')}){disp}")
    else:
        print("  (none yet)")
    print("Open Threads:")
    if threads:
        for t in threads:
            deadline = f" [deadline: turn {t['deadline_turn']}]" if t.get("deadline_turn") else ""
            print(f"  - {t.get('text')}{deadline}")
    else:
        print("  (none)")
    print("Throughline:")
    if throughline:
        for line in throughline:
            print(f"  - {line}")
    else:
        print("  (none yet)")


if __name__ == "__main__":
    main()
