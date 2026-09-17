#!/usr/bin/env python3
"""Bundle this campaign's save data into a single JSON file for archiving
or handing to another person -- the "download your adventure" analog.

Why this exists: saves/current.json, saves/journal.md, saves/locations.json
and saves/npc_registry.json already ARE the save, spread across separate
files plus git history. That's the right shape for this project to run
(git is the actual survivability mechanism -- see LOCAL.md), but it's not
a shape a person can casually hand to someone else the way Auferet's
"download as a file" export works: doing that today means finding and
sending four separate files (or a git bundle) and hoping none of them are
skipped or out of sync with each other. This script produces exactly one
file that captures a specific, self-consistent moment.

Deliberately excludes saves/player_notes.md by default: that file is
explicitly out-of-character player preferences, never narrated and never
canon (see saves/player_notes.md's own header and prompts/GM_INSTRUCTIONS.md),
so an export meant to be archived or shared with someone else should not
silently carry it along. Pass --include-player-notes if you specifically
want it (e.g. exporting only for your own backup, not to share).

This is read-only with respect to the save files themselves -- it never
modifies saves/current.json, journal.md, locations.json, or
npc_registry.json, only reads them into one output file. It has no
opinion on WHERE the campaign is narratively; it exports whatever is
currently committed, matching status_dump.py's "answer from the actual
file" principle rather than reconstructing anything from conversation
memory.

Usage:
    python3 scripts/export_save.py [output_path]
        Writes the bundle to output_path (default: saves/exports/<turn>-<UTC timestamp>.json).

    python3 scripts/export_save.py --include-player-notes [output_path]
        Also includes saves/player_notes.md's raw text in the bundle.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAVES_DIR = ROOT / "saves"
CURRENT_PATH = SAVES_DIR / "current.json"
JOURNAL_PATH = SAVES_DIR / "journal.md"
LOCATIONS_PATH = SAVES_DIR / "locations.json"
NPC_REGISTRY_PATH = SAVES_DIR / "npc_registry.json"
PLAYER_NOTES_PATH = SAVES_DIR / "player_notes.md"
EXPORT_DIR = SAVES_DIR / "exports"

EXPORT_FORMAT_VERSION = 1


def load_json_if_exists(path):
    """Returns the parsed JSON at path, or None if the file is missing or
    fails to parse -- a missing optional file (locations.json on an older
    campaign, npc_registry.json before any NPC was ever introduced) is a
    normal state, not an error that should abort the whole export."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, RecursionError):
        return None


def load_text_if_exists(path):
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def build_bundle(include_player_notes=False):
    """Assembles the export bundle as a plain dict. Kept separate from
    main() so a future script (or a REPL/test) can call this directly
    without going through argument parsing or writing a file."""
    current_state = load_json_if_exists(CURRENT_PATH)
    if current_state is None:
        raise FileNotFoundError(
            f"No saves/current.json found (or it failed to parse) at {CURRENT_PATH} "
            "-- nothing to export yet."
        )

    bundle = {
        "export_format_version": EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exported_from_turn": current_state.get("turn"),
        "current_state": current_state,
        "journal_md": load_text_if_exists(JOURNAL_PATH) or "",
        "locations": load_json_if_exists(LOCATIONS_PATH),
        "npc_registry": load_json_if_exists(NPC_REGISTRY_PATH) or {},
    }
    if include_player_notes:
        bundle["player_notes_md"] = load_text_if_exists(PLAYER_NOTES_PATH) or ""
    return bundle


def default_export_path(bundle):
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    turn = bundle.get("exported_from_turn", "unknown")
    return EXPORT_DIR / f"turn{turn}-{stamp}.json"


def main():
    parser = argparse.ArgumentParser(
        description="Bundle saves/current.json, journal.md, locations.json "
                     "and npc_registry.json into a single exportable file."
    )
    parser.add_argument("output", nargs="?", default=None,
                         help="Where to write the bundle. Defaults to "
                              "saves/exports/turn<N>-<UTC timestamp>.json.")
    parser.add_argument("--include-player-notes", action="store_true",
                         help="Also include saves/player_notes.md's raw text. "
                              "Omitted by default since that file is "
                              "out-of-character and not meant to be shared "
                              "or treated as campaign canon.")
    args = parser.parse_args()

    try:
        bundle = build_bundle(include_player_notes=args.include_player_notes)
    except FileNotFoundError as e:
        print(f"FAIL: {e}")
        sys.exit(1)

    output_path = Path(args.output) if args.output else default_export_path(bundle)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)
        f.write("\n")

    print(f"Exported turn {bundle.get('exported_from_turn')} to {output_path}")
    if args.include_player_notes:
        print("(includes player_notes.md -- do not hand this copy to another player)")
    else:
        print("(player_notes.md excluded -- pass --include-player-notes to include it)")


if __name__ == "__main__":
    main()
