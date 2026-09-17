#!/usr/bin/env python3
"""Keyword search over saves/journal.md -- the played-history counterpart
to world_info_lookup.py's search over static lore (docs/ELDARA_REFERENCE.md,
docs/CHAD_BACKSTORY.md).

Why this exists: world_info_lookup.py answers "what does the lore say"
but nothing in this project answers "what actually happened in play" other
than manually scrolling saves/journal.md. Auferet's Event Library does
this for emergent history -- session facts, not just authored lore --
by making the whole adventure a searchable document rather than only
handing the model whatever fits in a fixed recent-turns window. This
script is the same idea applied to journal.md's existing content: no new
data is captured, nothing here changes what commit_state.py writes, it
only makes what's already being recorded actually findable later.

This is read-only and advisory by construction -- like
lore_consistency_check.py, it never blocks a commit and has no opinion
on whether narration is correct. It answers "what does the journal say
about X", nothing more.

Usage:
    python3 scripts/journal_lookup.py <search term>
    python3 scripts/journal_lookup.py --npc <npc_id or name>
    python3 scripts/journal_lookup.py --turn <turn number>
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOURNAL_PATH = ROOT / "saves" / "journal.md"

# Splits journal.md into per-turn entries. Matches commit_state.py's own
# append_journal() format exactly ("### Turn N — <UTC timestamp>"), so a
# format change there needs a matching change here -- there's no shared
# constant between the two today, which is a real coupling worth noting
# if journal.md's format is ever revised (see this module's own
# docstring caveat further down).
ENTRY_HEADER_PATTERN = re.compile(r"^### Turn (\S+) — (.+)$", re.MULTILINE)


def load_entries():
    """Returns a list of {turn, timestamp, body} dicts, one per journal
    entry, in file order (oldest first, matching how commit_state.py
    appends). Returns an empty list if journal.md doesn't exist yet or
    has no entries -- both are normal early-campaign states, not errors,
    so callers don't need to special-case "no journal yet" separately
    from "no matches found"."""
    if not JOURNAL_PATH.exists():
        return []
    text = JOURNAL_PATH.read_text(encoding="utf-8")
    matches = list(ENTRY_HEADER_PATTERN.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        turn, timestamp = m.group(1), m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries.append({"turn": turn, "timestamp": timestamp, "body": text[start:end].strip()})
    return entries


def search_text(entries, term):
    """Case-insensitive substring search across each entry's full body
    (note + diff lines). Deliberately simple substring matching, not
    word-boundary matching like world_info_lookup.py's KEYWORDS lookup --
    journal entries are short, mechanical diff lines rather than prose,
    so the false-match risk that motivated word-boundary matching there
    (e.g. 'age' inside 'manager') is much smaller here, and a substring
    match is more forgiving for npc_id fragments and partial item names."""
    term_lower = term.lower()
    return [e for e in entries if term_lower in e["body"].lower() or term_lower in e["timestamp"].lower()]


def search_by_turn(entries, turn):
    return [e for e in entries if e["turn"] == str(turn)]


def main():
    parser = argparse.ArgumentParser(
        description="Search saves/journal.md for turns mentioning a term, "
                     "an NPC, or a specific turn number."
    )
    parser.add_argument("term", nargs="?", default=None,
                         help="Free-text search term (matched against the "
                              "whole entry body).")
    parser.add_argument("--npc", default=None,
                         help="Search for a specific npc_id or NPC name.")
    parser.add_argument("--turn", default=None,
                         help="Show the journal entry for one specific turn number.")
    args = parser.parse_args()

    if not any([args.term, args.npc, args.turn]):
        parser.print_help()
        sys.exit(0)

    entries = load_entries()
    if not entries:
        print("No journal entries found (saves/journal.md is empty or missing).")
        sys.exit(0)

    if args.turn is not None:
        results = search_by_turn(entries, args.turn)
        if not results:
            print(f"No journal entry found for turn {args.turn}.")
            sys.exit(0)
    else:
        term = args.npc if args.npc is not None else args.term
        results = search_text(entries, term)
        if not results:
            print(f"No journal entries mention: {term}")
            sys.exit(0)

    print(f"Found {len(results)} matching journal entr{'y' if len(results) == 1 else 'ies'}:\n")
    for e in results:
        print(f"=== Turn {e['turn']} — {e['timestamp']} ===")
        print(e["body"])
        print()


if __name__ == "__main__":
    main()
