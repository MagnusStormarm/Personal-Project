#!/usr/bin/env python3
"""One-step lore registration: append a new section to docs/ELDARA_REFERENCE.md
or docs/CHAD_BACKSTORY.md and/or register keyword(s) pointing to a section in
docs/lore_keywords.json, instead of hand-editing prose and JSON separately.

Why this exists: docs/lore_keywords.json (see world_info_lookup.py) already
turned "add a lore keyword" into a data edit instead of a code edit, but
adding NEW lore was still a two-step manual process either way -- write the
section in the doc file, then separately open lore_keywords.json and wire up
retrieval for it. This script does both in one command when both are needed,
or just the keyword-registration half when the section already exists.

This does NOT write lore prose FOR you -- the actual worldbuilding content is
still the GM's/player's own creative call, supplied via --body or
--body-file. This only handles the mechanical wiring: appending a section in
the exact format world_info_lookup.py's own parser expects, and/or
registering keyword(s) against it.

Usage:
    # Register keyword(s) against an EXISTING section:
    python3 scripts/add_lore.py --source world --section 2.16 --keywords "guild hall,artisans"
    python3 scripts/add_lore.py --source chad --section "New Habit" --keywords "nervous tic"

    # Add a brand-new section AND register keywords for it in one step:
    python3 scripts/add_lore.py --source world --section 2.16 --heading "Artisan Guilds" \\
        --body "Prose here..." --keywords "guild hall,artisans"
    python3 scripts/add_lore.py --source chad --section "New Habit" \\
        --body-file /tmp/draft.txt --keywords "nervous tic"

For --source chad, --section IS the heading text (Chad's backstory file has
no numbering scheme -- see world_info_lookup.py's _load_chad_sections);
--heading is only meaningful, and only required alongside --body/--body-file,
for --source world.
"""
import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import world_info_lookup as wil  # noqa: E402

ROOT = SCRIPTS_DIR.parent


def load_keywords_raw():
    """Reads docs/lore_keywords.json as a plain dict, tolerating a
    missing or malformed file the same way world_info_lookup.py's own
    load_keywords() does -- this script writes that same file, so it
    needs the raw, still-serializable form (source as a string tag),
    not wil.KEYWORDS's already-resolved Path form."""
    if not wil.KEYWORDS_PATH.exists():
        return {}
    try:
        return json.loads(wil.KEYWORDS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, RecursionError):
        return {}


def save_keywords_raw(data):
    with open(wil.KEYWORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def section_exists(source_path, section_key, is_world):
    text = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
    sections = wil._load_world_sections(text) if is_world else wil._load_chad_sections(text)
    return section_key in sections


def append_section(source_path, section_key, heading, body, is_world):
    """Appends a new section to the doc file, formatted exactly the way
    world_info_lookup.py's WORLD_SECTION_PATTERN / CHAD_SECTION_PATTERN
    expect ("## N.N Heading" for world reference, "## Heading" for
    Chad's backstory) -- reuses that module's own section-splitting
    helpers to confirm the section doesn't already exist, so this script
    and world_info_lookup.py can never disagree about what counts as a
    section boundary."""
    heading_line = f"## {section_key} {heading}" if is_world else f"## {heading}"
    text = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    text += f"\n{heading_line}\n\n{body.strip()}\n"
    source_path.write_text(text, encoding="utf-8")


def register_keywords(keywords, source_tag, section_key):
    raw = load_keywords_raw()
    added = []
    for kw in keywords:
        existing = raw.get(kw)
        if existing and existing.get("source") == source_tag:
            sections = existing.get("sections", [])
            if section_key not in sections:
                sections.append(section_key)
            existing["sections"] = sections
        else:
            if existing:
                print(f"  NOTE: '{kw}' previously pointed to {existing.get('source')} "
                      f"{existing.get('sections')} -- overwriting to point only at "
                      f"{source_tag} {section_key!r}.")
            raw[kw] = {"source": source_tag, "sections": [section_key]}
        added.append(kw)
    save_keywords_raw(raw)
    return added


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", choices=["world", "chad"], required=True,
                         help="world -> docs/ELDARA_REFERENCE.md, chad -> docs/CHAD_BACKSTORY.md")
    parser.add_argument("--section", required=True,
                         help="Section id (world, e.g. '2.16') or the section's exact "
                              "heading text (chad, which has no numbering scheme).")
    parser.add_argument("--heading", default=None,
                         help="Heading text for a NEW world section. Required alongside "
                              "--body/--body-file when --source is world; ignored for chad, "
                              "where --section already IS the heading.")
    parser.add_argument("--body", default=None, help="New section body text.")
    parser.add_argument("--body-file", default=None,
                         help="Path to a file containing the new section's body text, "
                              "as an alternative to --body for longer prose.")
    parser.add_argument("--keywords", default=None,
                         help="Comma-separated keyword(s) to register against this section.")
    args = parser.parse_args()

    is_world = args.source == "world"
    source_path = wil.WORLD_REFERENCE if is_world else wil.CHAD_REFERENCE
    section_key = args.section

    if args.body is not None and args.body_file is not None:
        print("FAIL: give at most one of --body / --body-file, not both.")
        sys.exit(1)

    body_text = None
    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.exists():
            print(f"FAIL: --body-file not found: {body_path}")
            sys.exit(1)
        body_text = body_path.read_text(encoding="utf-8")
    elif args.body is not None:
        body_text = args.body

    exists = section_exists(source_path, section_key, is_world)

    if body_text is not None:
        if exists:
            print(f"FAIL: section {section_key!r} already exists in {source_path.name} -- "
                  "not overwriting. Edit the file directly if you need to revise existing lore.")
            sys.exit(1)
        if is_world and not args.heading:
            print("FAIL: --heading is required alongside --body/--body-file for --source world.")
            sys.exit(1)
        if not body_text.strip():
            print("FAIL: --body/--body-file was empty.")
            sys.exit(1)
        append_section(source_path, section_key, args.heading or section_key, body_text, is_world)
        print(f"Added new section {section_key!r} to {source_path.relative_to(ROOT)}.")
    elif not exists:
        print(f"FAIL: section {section_key!r} not found in {source_path.name}, and no "
              "--body/--body-file given to create it. Pass --body (or --body-file) and, "
              "for --source world, --heading, to add it as a new section.")
        sys.exit(1)

    if args.keywords:
        keywords = [k.strip().lower() for k in args.keywords.split(",") if k.strip()]
        if not keywords:
            print("FAIL: --keywords was given but contained no usable keyword.")
            sys.exit(1)
        added = register_keywords(keywords, args.source, section_key)
        print(f"Registered keyword(s) in {wil.KEYWORDS_PATH.relative_to(ROOT)}: {', '.join(added)}")
    elif body_text is None:
        print("Nothing to do -- pass --keywords and/or --body/--body-file.")


if __name__ == "__main__":
    main()
