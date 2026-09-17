#!/usr/bin/env python3
"""List the GM's situational cases -- every "when X happens, do Y" the GM
is on the hook for -- from docs/gm_cases.json, and say which of them are
live against the current save right now.

Why this exists: prompts/GM_INSTRUCTIONS.md is the contract, but it's
1,500 words of prose and the obligations in it are scattered across two
parts and twenty-odd headings. Mid-scene, the question a GM actually has
is narrow ("the player just said 'audit state' -- what exactly am I
supposed to run?", "an NPC from turn 12 just walked back on -- new id or
old?"), and re-reading the whole contract to answer it is exactly the
kind of thing that gets skipped under time pressure and turns into drift.
This is the index over that contract: trigger on the left, required
action on the right, one screen at a time.

Two things this deliberately is NOT:

  * It is not a replacement for GM_INSTRUCTIONS.md, and it does not add,
    soften, or reinterpret a single rule. Every case carries the exact
    heading it was extracted from, and --check-sources fails loudly if a
    heading stops existing -- so restructuring the instructions surfaces
    as a broken pointer rather than a quietly stale summary. If this
    file and the instructions ever disagree, the instructions win.
  * It is not a judge. --due reports only what can be read mechanically
    off saves/current.json (turn 0, a multiple-of-20 turn, an array at
    its soft cap, a passed deadline, travel in progress, perishables
    held). The cases with no live_check -- which is most of them, since
    "a scene calls for a solution from Chad" isn't a JSON field -- are
    always listed and never claimed to be due or not due. Same posture
    as world_info_lookup.py and location_lookup.py: it answers "what does
    the file say", it does not decide what the story needs.

Usage:
    python3 scripts/gm_cases.py                    # every case, grouped
    python3 scripts/gm_cases.py --list-gm-cases    # same thing
    python3 scripts/gm_cases.py npc                # cases matching text
    python3 scripts/gm_cases.py --category player
    python3 scripts/gm_cases.py --due              # live against the save
    python3 scripts/gm_cases.py --due --state /tmp/proposed_state.json
    python3 scripts/gm_cases.py --check-sources    # instructions drift
    python3 scripts/gm_cases.py --json
"""
import argparse
import hashlib
import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "docs" / "gm_cases.json"
# Short enough to read in a diff, long enough that collisions are not a
# practical concern across a few dozen sections.
DIGEST_LEN = 12
CURRENT_PATH = ROOT / "saves" / "current.json"
INSTRUCTIONS_PATH = ROOT / "prompts" / "GM_INSTRUCTIONS.md"
SCHEMA_PATH = ROOT / "state_schema.json"

# Mirrors scripts/validate_state.py's SOFT_CAPS. Duplicated rather than
# imported because this script is read-only and advisory: it should keep
# working (and keep being safe to run mid-scene) even if the validator
# grows an import-time dependency. validate_state.py stays authoritative
# -- a mismatch here shows up as a --due line that's early or late, never
# as a state that got committed over cap.
SOFT_CAPS = {
    "npc_relationships": 10,
    "open_threads": 8,
    "continuity_notes": 5,
    "throughline": 6,
}

CATEGORY_ORDER = ["every-turn", "player", "state", "state-change", "tooling"]

CATEGORY_BLURBS = {
    "every-turn": "Standing obligations -- these apply to every reply, not to a specific event.",
    "player": "The player said a specific thing and it obligates a specific response.",
    "state": "A condition the save file itself can put you in.",
    "state-change": "The turn changed Chad's state -- the commit pipeline's cases.",
    "tooling": "Reach for a script instead of memory or invention.",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_cases():
    """Returns the parsed case list. A missing or malformed
    docs/gm_cases.json is a real breakage (unlike a missing
    locations.json, which is a legitimate campaign state), so this
    prints and exits rather than returning None for callers to handle."""
    try:
        with open(CASES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, RecursionError) as exc:
        print(f"Could not read {CASES_PATH.relative_to(ROOT)}: {exc}")
        sys.exit(1)
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        print(f"{CASES_PATH.relative_to(ROOT)} has no 'cases' array.")
        sys.exit(1)
    return cases


def load_state(path):
    """Returns the parsed state dict, or None if it's missing or
    unparseable -- callers print their own message. A campaign that
    hasn't been started yet has no current.json, and that's a normal
    thing to run this script against, not an error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, RecursionError):
        return None


def month_order():
    """Month names in calendar order, read from state_schema.json's own
    enum rather than hardcoded here -- the calendar is defined there and
    in docs/ELDARA_REFERENCE.md, and a second copy of it in this script
    is one more thing that could silently disagree. Returns [] if the
    schema can't be read, which just means date comparison is skipped."""
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = json.load(f)
        return list(schema["properties"]["in_world_date"]["properties"]["month"]["enum"])
    except (json.JSONDecodeError, OSError, RecursionError, KeyError, TypeError):
        return []


def date_tuple(date):
    """A sortable (year, month index, day) for an in_world_date dict, or
    None if it can't be ordered confidently."""
    months = month_order()
    if not isinstance(date, dict) or not months:
        return None
    month = date.get("month")
    if month not in months:
        return None
    year, day = date.get("year"), date.get("day")
    if not isinstance(year, int) or not isinstance(day, int):
        return None
    return (year, months.index(month), day)


# ---------------------------------------------------------------------------
# Live checks
#
# Each takes the loaded state and returns (is_due, [detail lines]). They
# only ever read fields that are mechanically unambiguous -- a turn
# number, an array length, a deadline integer. Anything needing a reading
# of the narration is deliberately left without a check rather than
# guessed at.
# ---------------------------------------------------------------------------

def check_turn_zero(state):
    turn = state.get("turn")
    if turn == 0:
        gear = [g.get("name") for g in state.get("gear", []) if isinstance(g, dict)]
        return True, [f"turn 0; gear currently: {', '.join(gear) if gear else '(none)'}"]
    return False, []


def check_turn_multiple_of_20(state):
    turn = state.get("turn")
    if isinstance(turn, int) and turn > 0 and turn % 20 == 0:
        return True, [f"turn {turn} is a multiple of 20 -- the automatic audit is due this turn"]
    return False, []


def check_perishables_held(state):
    held = [g.get("name", "(unnamed)") for g in state.get("gear", [])
            if isinstance(g, dict) and g.get("perishable")]
    if held:
        return True, [f"perishable gear held: {', '.join(held)}"]
    return False, []


def check_soft_cap_reached(state):
    details = []
    for field, cap in SOFT_CAPS.items():
        items = state.get(field)
        if isinstance(items, list) and len(items) >= cap:
            at_or_over = "over" if len(items) > cap else "at"
            details.append(f"{field}: {len(items)}/{cap} ({at_or_over} cap) -- "
                           f"run: python3 scripts/prune_advisor.py {field}")
    return bool(details), details


def check_deadline_passed(state):
    turn = state.get("turn")
    if not isinstance(turn, int):
        return False, []
    details = []
    for thread in state.get("open_threads", []):
        if not isinstance(thread, dict) or not thread.get("active"):
            continue
        deadline = thread.get("deadline_turn")
        if not isinstance(deadline, int) or turn < deadline:
            continue
        text = str(thread.get("text", "(untitled thread)"))
        if turn == deadline:
            details.append(f"window closes this turn (deadline_turn {deadline}): {text}")
        else:
            details.append(f"deadline_turn {deadline} passed {turn - deadline} turn(s) ago: {text}")
    return bool(details), details


def check_travel_in_progress(state):
    travel = state.get("travel")
    if not isinstance(travel, dict) or not travel:
        return False, []
    destination = travel.get("destination", "(unset destination)")
    eta = travel.get("eta_date")
    line = f"en route to {destination}"
    now_t, eta_t = date_tuple(state.get("in_world_date")), date_tuple(eta)
    if now_t and eta_t:
        if now_t >= eta_t:
            line += " -- ETA reached; the next commit clears travel and sets current_location"
        else:
            line += f" -- ETA {eta.get('day')} {eta.get('month')} {eta.get('year')}, not yet reached"
    return True, [line]


LIVE_CHECKS = {
    "turn_zero": check_turn_zero,
    "turn_multiple_of_20": check_turn_multiple_of_20,
    "perishables_held": check_perishables_held,
    "soft_cap_reached": check_soft_cap_reached,
    "deadline_passed": check_deadline_passed,
    "travel_in_progress": check_travel_in_progress,
}


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def wrap(text, indent):
    return textwrap.fill(text, width=78, initial_indent=indent,
                         subsequent_indent=indent)


def labelled(label, text):
    """A WHEN/DO/NOW line whose wrapped continuation hangs under the text
    rather than under the label, so a long action still reads as one
    block at a glance."""
    return textwrap.fill(text, width=78,
                         initial_indent=f"    {label:<6}",
                         subsequent_indent=" " * 10)


def format_case(case, details=None):
    lines = [f"  [{case['id']}]",
             labelled("WHEN", case["trigger"]),
             labelled("DO", case["action"])]
    for detail in details or []:
        lines.append(labelled("NOW", detail))
    lines.append(f"    ({case['source']})")
    return "\n".join(lines)


def print_grouped(cases, details_by_id=None):
    details_by_id = details_by_id or {}
    categories = [c for c in CATEGORY_ORDER if any(k["category"] == c for k in cases)]
    categories += sorted({k["category"] for k in cases} - set(CATEGORY_ORDER))
    for category in categories:
        in_category = [k for k in cases if k["category"] == category]
        print(f"\n{category.upper()}  ({len(in_category)})")
        blurb = CATEGORY_BLURBS.get(category)
        if blurb:
            print(wrap(blurb, "  "))
        print()
        for case in in_category:
            print(format_case(case, details_by_id.get(case["id"])))
            print()


# ---------------------------------------------------------------------------
# --check-sources
# ---------------------------------------------------------------------------

def instruction_headings():
    """Every markdown heading in GM_INSTRUCTIONS.md, as exact text."""
    if not INSTRUCTIONS_PATH.exists():
        return None
    headings = []
    for line in INSTRUCTIONS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            headings.append(stripped.lstrip("#").strip())
    return headings


def instruction_sections():
    """Each heading in GM_INSTRUCTIONS.md mapped to a digest of its body.

    A heading pointer catches restructuring. It cannot catch the prose
    under a heading being rewritten while the heading stays put -- which
    is the more common edit, and which leaves a case still pointing
    somewhere real while describing a procedure that has changed.
    Digesting the body closes that gap.

    Whitespace is collapsed before hashing, so rewrapping a paragraph is
    not drift but any changed word is. A heading appearing more than once
    has all of its bodies digested together.
    """
    if not INSTRUCTIONS_PATH.exists():
        return None
    bodies, current, buf = {}, None, []
    for line in INSTRUCTIONS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            if current is not None:
                bodies.setdefault(current, []).append("\n".join(buf))
            current, buf = line.strip().lstrip("#").strip(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        bodies.setdefault(current, []).append("\n".join(buf))
    return {
        heading: hashlib.sha256(
            re.sub(r"\s+", " ", " ".join(parts)).strip().encode("utf-8")
        ).hexdigest()[:DIGEST_LEN]
        for heading, parts in bodies.items()
    }


def cmd_refresh_digests(cases):
    """Re-record every case's source_digest against the current prose.

    Run after reading the drifted cases --check-sources named and
    confirming each still describes what its section says. Deliberately a
    separate, explicit command: refreshing automatically would make the
    check self-silencing, which is the failure mode it exists to prevent.
    """
    digests = instruction_sections()
    if digests is None:
        print(f"MISSING: {INSTRUCTIONS_PATH.relative_to(ROOT)} -- cannot refresh.")
        return 1
    data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    changed = 0
    for case in data["cases"]:
        new = digests.get(case["source"])
        if new is None:
            print(f"  skipped {case['id']}: source heading not found")
            continue
        if case.get("source_digest") != new:
            case["source_digest"] = new
            changed += 1
    CASES_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {changed} digest(s); {len(data['cases'])} cases total.")
    return 0


def cmd_check_sources(cases):
    """Fails if any case points at a heading that no longer exists, or
    names a live_check this script doesn't implement. This is the whole
    reason the cases carry a 'source' at all: the failure mode for a
    derived list like this one is going stale silently while still
    reading as authoritative, and a pointer that can be mechanically
    checked is the cheapest defense against that."""
    ok = True

    headings = instruction_headings()
    if headings is None:
        print(f"MISSING: {INSTRUCTIONS_PATH.relative_to(ROOT)} -- cannot check sources.")
        return 1

    print(f"Checking {len(cases)} cases against "
          f"{INSTRUCTIONS_PATH.relative_to(ROOT)} ({len(headings)} headings)\n")

    missing = [(c["id"], c["source"]) for c in cases if c["source"] not in headings]
    if missing:
        ok = False
        print("Cases whose source heading no longer exists:")
        for case_id, source in missing:
            print(f"  {case_id}: \"{source}\"")
        print("\n  Fix docs/gm_cases.json to point at the heading's new text "
              "(or drop the case if the rule itself is gone).\n")
    else:
        print("Every case's source heading still exists.\n")

    unknown = sorted({c["live_check"] for c in cases
                      if c.get("live_check") and c["live_check"] not in LIVE_CHECKS})
    if unknown:
        ok = False
        print("Cases naming a live_check this script doesn't implement:")
        for name in unknown:
            print(f"  {name}")
        print()

    # Content drift is reported but does NOT fail this check, and that is
    # a deliberate split rather than leniency. A vanished heading is
    # unambiguous: the pointer is broken. A rewritten body is a question --
    # the first run of this found two drifted sections and only one left
    # its case actually wrong; the other case never quoted the sentence
    # that changed. Failing on every prose edit would turn
    # `session.py audit` red for documentation work, and an audit people
    # learn to ignore protects nothing. So: named loudly, every run,
    # without blocking.
    digests = instruction_sections()
    if digests is not None:
        drifted = [(c["id"], c["source"], c["source_digest"], digests[c["source"]])
                   for c in cases
                   if c.get("source_digest") and c["source"] in digests
                   and c["source_digest"] != digests[c["source"]]]
        unrecorded = [c["id"] for c in cases if not c.get("source_digest")]
        if drifted:
            print("Cases whose source section has been REWRITTEN since extraction")
            print("(heading still exists -- read each case against its section):")
            for case_id, source, was, now in drifted:
                print(f"  {case_id}: \"{source}\"  {was} -> {now}")
            print("\n  Once each still reads true, re-record with "
                  "`gm_cases.py --refresh-digests`.\n")
        if unrecorded:
            print(f"{len(unrecorded)} case(s) carry no source_digest, so content "
                  "drift cannot be detected for them:")
            print("  " + ", ".join(unrecorded))
            print("\n  Run `gm_cases.py --refresh-digests` to start tracking them.\n")
        if not drifted and not unrecorded:
            print("Every case's source section is unchanged since extraction.\n")

    # Informational only: a heading with no case under it is usually fine
    # (the Design Pillars and Prose Craft sections are guidance for how to
    # write, not discrete triggers), but a NEW one showing up here is a
    # useful nudge that a rule may have been added without a case.
    uncovered = [h for h in headings
                 if h not in {c["source"] for c in cases}
                 and not h.startswith("Part ")
                 and not h.startswith("ELDARA GM")]
    if uncovered:
        print("Headings with no case pointing at them (informational, not a failure):")
        for heading in uncovered:
            print(f"  {heading}")
        print()

    print("SOURCES OK." if ok else "SOURCE DRIFT -- see above.")
    return 0 if ok else 1


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="List the GM's situational cases (trigger -> required "
                     "action) from docs/gm_cases.json, and which are live "
                     "against the current save."
    )
    parser.add_argument("query", nargs="*", default=None,
                         help="Only show cases matching this text "
                              "(id, trigger, action, or source).")
    parser.add_argument("--refresh-digests", action="store_true",
                         help="Re-record each case's source_digest against the current "
                              "GM_INSTRUCTIONS.md, after confirming the cases still read "
                              "true. Run when --check-sources reports drift.")
    parser.add_argument("--list-gm-cases", action="store_true",
                         help="List every case -- the default behavior, "
                              "spelled out.")
    parser.add_argument("--due", action="store_true",
                         help="Only cases whose condition is mechanically "
                              "true against the save right now.")
    parser.add_argument("--state", default=None,
                         help="State file for --due (default: "
                              "saves/current.json). Point this at a proposed "
                              "state to check it before committing.")
    parser.add_argument("--category", default=None,
                         help=f"Only one category: {', '.join(CATEGORY_ORDER)}.")
    parser.add_argument("--check-sources", action="store_true",
                         help="Verify every case still points at a real "
                              "heading in prompts/GM_INSTRUCTIONS.md. "
                              "Exits non-zero on drift.")
    parser.add_argument("--json", action="store_true",
                         help="Machine-readable output.")
    args = parser.parse_args()

    cases = load_cases()

    if args.refresh_digests:
        sys.exit(cmd_refresh_digests(cases))

    if args.check_sources:
        sys.exit(cmd_check_sources(cases))

    if args.category:
        wanted = args.category.strip().lower()
        cases = [c for c in cases if c["category"] == wanted]
        if not cases:
            print(f"No cases in category '{args.category}'. "
                  f"Categories: {', '.join(CATEGORY_ORDER)}")
            sys.exit(0)

    if args.query:
        needle = " ".join(args.query).strip().lower()
        cases = [c for c in cases
                 if needle in " ".join([c["id"], c["trigger"], c["action"],
                                        c["source"], c["category"]]).lower()]
        if not cases:
            print(f"No case matches '{' '.join(args.query)}'. "
                  f"Run with no arguments to see all of them.")
            sys.exit(0)

    details_by_id = {}
    state = None
    if args.due:
        state_path = Path(args.state) if args.state else CURRENT_PATH
        state = load_state(state_path)
        if state is None:
            print(f"No readable state at {state_path} -- nothing to check "
                  "cases against. Run without --due to see every case.")
            sys.exit(0)
        due = []
        for case in cases:
            check = LIVE_CHECKS.get(case.get("live_check"))
            if check is None:
                continue
            is_due, details = check(state)
            if is_due:
                due.append(case)
                details_by_id[case["id"]] = details
        cases = due

    if args.json:
        print(json.dumps([dict(c, now=details_by_id.get(c["id"], []))
                          for c in cases], indent=2))
        return

    if args.due:
        turn = state.get("turn")
        print("=" * 70)
        print(f"GM CASES LIVE RIGHT NOW (turn {turn})")
        print("=" * 70)
        if not cases:
            print("\nNo mechanically-checkable case is live against this state.")
        else:
            print_grouped(cases, details_by_id)
        print(wrap("Only cases with a mechanical condition can appear here. The "
                   "rest of the list -- everything that depends on what's "
                   "actually happening in the scene -- is never 'not due'. Run "
                   "without --due for the full contract.", ""))
        return

    print("=" * 70)
    print(f"GM CASES  ({len(cases)})")
    print("=" * 70)
    print(wrap("Extracted from prompts/GM_INSTRUCTIONS.md, which remains "
               "authoritative -- this is an index over it, not a replacement "
               "for reading it. Each case ends with the heading it came from.", ""))
    print_grouped(cases)


if __name__ == "__main__":
    main()
